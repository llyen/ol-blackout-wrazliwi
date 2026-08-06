"""Weryfikacja raportu OL_BLK_Report.

Fabric waliduje strukture PBIR przy zapisie, ale NIE sprawdza, czy pole
istnieje w modelu - literowka w nazwie miary nie powoduje bledu przy
publikacji, tylko pusty wizual przed oczami decydenta. Ten skrypt:

  1. pobiera definicje raportu z Fabric,
  2. sprawdza liczbe stron (oczekiwana = liczba stron w create_report.py),
  3. wyciaga wszystkie odwolania do miar i kolumn,
  4. potwierdza offline, ze kazde odwolanie istnieje w model_spec.py /
     lakehouse_schemas.json,
  5. potwierdza online zapytaniem DAX (executeQueries), ze kazda miara
     i kolumna faktycznie rozwiazuje sie w modelu semantycznym.

Uzycie:
    python deploy/verify_report.py
"""
from __future__ import annotations

import base64
import importlib.util
import json
import pathlib
import subprocess
import sys
import time
from collections import defaultdict

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
SCHEMAS = ROOT / "deploy" / "lakehouse_schemas.json"
MODEL_SPEC = ROOT / "deploy" / "model_spec.py"
CREATE = ROOT / "deploy" / "create_report.py"
REPORT_NAME = "OL_BLK_Report"
FABRIC_API = "https://api.fabric.microsoft.com/v1"
PBI_API = "https://api.powerbi.com/v1.0/myorg"
FABRIC_RES = "https://api.fabric.microsoft.com"
PBI_RES = "https://analysis.windows.net/powerbi/api"


def bearer(tok: str) -> str:
    return " ".join(("Bearer", tok))


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def _load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = [argv[0]]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


def model_metadata() -> tuple[dict[str, set[str]], dict[str, str]]:
    mod = _load_module(MODEL_SPEC, "_ms")
    schemas = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    hidden = getattr(mod, "HIDDEN_TABLES", set())
    columns = {tbl: {c[0] for c in fields} for tbl, fields in schemas.items()
               if tbl not in hidden}
    measures = {m[0]: tbl for tbl, group in mod.MEASURES.items() for m in group}
    return columns, measures


def expected_pages() -> int:
    return len(_load_module(CREATE, "_cr").PAGE_BUILDERS)


def find_report(ws: str, tk: str) -> str:
    r = requests.get(f"{FABRIC_API}/workspaces/{ws}/reports",
                     headers={"Authorization": bearer(tk)}, timeout=120)
    r.raise_for_status()
    item = next((i for i in r.json().get("value", []) if i["displayName"] == REPORT_NAME), None)
    if not item:
        sys.exit(f"Nie znaleziono raportu {REPORT_NAME} w obszarze {ws}.")
    return item["id"]


def get_definition(ws: str, rid: str, tk: str) -> list[dict]:
    hdr = {"Authorization": bearer(tk)}
    r = requests.post(f"{FABRIC_API}/workspaces/{ws}/reports/{rid}/getDefinition",
                      headers=hdr, timeout=300)
    if r.status_code == 202:
        op = r.headers["x-ms-operation-id"]
        for _ in range(60):
            time.sleep(2)
            s = requests.get(f"{FABRIC_API}/operations/{op}", headers=hdr, timeout=60).json().get("status")
            if s not in ("NotStarted", "Running"):
                break
        r = requests.get(f"{FABRIC_API}/operations/{op}/result", headers=hdr, timeout=300)
    r.raise_for_status()
    return r.json()["definition"]["parts"]


def collect_refs(parts: list[dict]) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, int]]:
    cols: dict[str, set[str]] = defaultdict(set)
    meas: dict[str, set[str]] = defaultdict(set)
    stats: dict[str, int] = defaultdict(int)
    for p in parts:
        if not p["path"].endswith("visual.json"):
            continue
        page = p["path"].split("/")[2]
        doc = json.loads(base64.b64decode(p["payload"]).decode("utf-8"))
        stats[page] += 1
        qs = doc["visual"].get("query", {}).get("queryState", {})
        for block in qs.values():
            for proj in block["projections"]:
                f = proj["field"]
                if "Measure" in f:
                    meas[f["Measure"]["Expression"]["SourceRef"]["Entity"]].add(f["Measure"]["Property"])
                else:
                    c = f["Aggregation"]["Expression"]["Column"] if "Aggregation" in f else f["Column"]
                    cols[c["Expression"]["SourceRef"]["Entity"]].add(c["Property"])
    return cols, meas, stats


def dax(ws: str, sm: str, tk: str, query: str) -> tuple[bool, str]:
    r = requests.post(f"{PBI_API}/groups/{ws}/datasets/{sm}/executeQueries",
                      headers={"Authorization": bearer(tk), "Content-Type": "application/json"},
                      json={"queries": [{"query": query}]}, timeout=300)
    if r.status_code != 200:
        try:
            det = r.json()["error"]["pbi.error"]["details"]
            msg = "; ".join(d["detail"]["value"] for d in det)
        except Exception:
            msg = r.text[:300]
        return False, msg
    return True, ""


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, sm = state["workspaceId"], state["semanticModelId"]

    columns, measures = model_metadata()
    exp_pages = expected_pages()

    fab_tk = token(FABRIC_RES)
    rid = state.get("reportId") or find_report(ws, fab_tk)
    print(f"Raport {REPORT_NAME}: {rid}")

    parts = get_definition(ws, rid, fab_tk)
    cols, meas, stats = collect_refs(parts)
    n_pages, n_vis = len(stats), sum(stats.values())
    print(f"  {len(parts)} czesci, {n_pages} stron, {n_vis} wizualizacji")
    for page in sorted(stats):
        print(f"    {page}: {stats[page]} wiz.")

    problems: list[str] = []
    if n_pages != exp_pages:
        problems.append(f"Liczba stron {n_pages} != oczekiwana {exp_pages}")

    # --- kontrola offline: literowki wzgledem spec ---
    print("\nKontrola offline (spec):")
    off = 0
    for tbl in sorted(meas):
        for m in sorted(meas[tbl]):
            if m not in measures:
                problems.append(f"Miara nieznana w spec: '{tbl}'[{m}] (literowka?)")
                off += 1
            elif measures[m] != tbl:
                problems.append(f"Miara '{m}' nalezy do '{measures[m]}', nie '{tbl}'")
                off += 1
    for tbl in sorted(cols):
        if tbl not in columns:
            problems.append(f"Tabela nieznana w spec: '{tbl}'")
            off += 1
            continue
        for c in sorted(cols[tbl]):
            if c not in columns[tbl]:
                problems.append(f"Kolumna nieznana w spec: '{tbl}'[{c}] (literowka?)")
                off += 1
    print(f"  {off} rozbieznosci ze specyfikacja")

    # --- kontrola online: DAX executeQueries ---
    pbi_tk = token(PBI_RES)
    ok = fail = 0
    print("\nKontrola online (DAX) - kolumny:")
    for tbl in sorted(cols):
        sel = ", ".join(f'"{c}", \'{tbl}\'[{c}]' for c in sorted(cols[tbl]))
        good, msg = dax(ws, sm, pbi_tk, f"EVALUATE TOPN(1, SELECTCOLUMNS('{tbl}', {sel}))")
        n = len(cols[tbl])
        if good:
            ok += n
            print(f"  OK   {tbl}: {n} kolumn")
        else:
            fail += n
            print(f"  BLAD {tbl}: {n} kolumn -> {msg}")
            problems.append(f"{tbl} (kolumny): {msg}")

    print("\nKontrola online (DAX) - miary:")
    for tbl in sorted(meas):
        for m in sorted(meas[tbl]):
            good, msg = dax(ws, sm, pbi_tk, f'EVALUATE ROW("v", \'{tbl}\'[{m}])')
            if good:
                ok += 1
                print(f"  OK   {tbl}[{m}]")
            else:
                fail += 1
                print(f"  BLAD {tbl}[{m}] -> {msg}")
                problems.append(f"{tbl}[{m}]: {msg}")

    print(f"\nWynik: {ok}/{ok + fail} odwolan DAX rozwiazuje sie w modelu; "
          f"{n_pages}/{exp_pages} stron")
    if problems:
        print(f"\nDo naprawy ({len(problems)}):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"\nRaport zweryfikowany. https://app.powerbi.com/groups/{ws}/reports/{rid}")


if __name__ == "__main__":
    main()
