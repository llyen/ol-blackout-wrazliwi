"""Kontrola modelu semantycznego: wykonanie DAX dla kazdej miary.

Model, ktory sie zapisal, nie musi jeszcze liczyc — bledy w Direct Lake
(zla kolumna, niedostepna tabela, dwuznaczna sciezka relacji) ujawniaja sie
dopiero przy zapytaniu. Ten skrypt odpytuje kazda miare osobno, zeby jeden
blad nie ukryl pozostalych, i zapisuje semanticModelId do deployment.json.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
STATE_PATH = BASE / ".fabric" / "deployment.json"
STATE = json.loads(STATE_PATH.read_text(encoding="utf-8"))
WS = STATE["workspaceId"]
NAME = "OL_BLK_SemanticModel"
FABRIC = "https://api.fabric.microsoft.com/v1"
PBI = "https://api.powerbi.com/v1.0/myorg"
FABRIC_RES = "https://api.fabric.microsoft.com"
PBI_RES = "https://analysis.windows.net/powerbi/api"


def auth(tok: str) -> str:
    return " ".join(("Bearer", tok))


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        raise SystemExit(out.stderr)
    return out.stdout.strip()


def measure_names() -> list[str]:
    """Lista miar czytana z modulu tworzacego model — jedno zrodlo prawdy."""
    spec = importlib.util.spec_from_file_location(
        "_csm", Path(__file__).with_name("model_spec.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.argv = [sys.argv[0]]
    spec.loader.exec_module(mod)
    return [m[0] for group in mod.MEASURES.values() for m in group]


def model_id() -> str:
    r = requests.get(f"{FABRIC}/workspaces/{WS}/semanticModels",
                     headers={"Authorization": auth(token(FABRIC_RES))},
                     timeout=120)
    r.raise_for_status()
    for item in r.json()["value"]:
        if item["displayName"] == NAME:
            return item["id"]
    raise SystemExit(f"Nie znaleziono modelu {NAME} w obszarze {WS}.")


def dax(model: str, query: str, pbi_token: str) -> tuple[bool, object]:
    r = requests.post(
        f"{PBI}/groups/{WS}/datasets/{model}/executeQueries",
        headers={"Authorization": auth(pbi_token), "Content-Type": "application/json"},
        json={"queries": [{"query": query}], "serializerSettings": {"includeNulls": True}},
        timeout=300)
    if r.status_code != 200:
        return False, r.text[:400]
    rows = r.json()["results"][0]["tables"][0]["rows"]
    return True, rows


def main() -> None:
    model = model_id()
    print(f"model {NAME}: {model}")
    if STATE.get("semanticModelId") != model:
        STATE["semanticModelId"] = model
        STATE_PATH.write_text(json.dumps(STATE, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
        print("zapisano semanticModelId do deployment.json")

    pbi = token(PBI_RES)
    names = measure_names()
    print(f"\n== {len(names)} miar")
    bad = []
    for name in names:
        ok, res = dax(model, f'EVALUATE ROW("v", [{name}])', pbi)
        if not ok:
            bad.append((name, res))
            print(f"   BLAD {name:<38} {str(res)[:120]}")
            continue
        val = res[0].get("[v]")
        flag = "OK " if val is not None else "PUSTA"
        if val is None:
            bad.append((name, "wartosc pusta"))
        shown = f"{val:,.4f}".rstrip("0").rstrip(".") if isinstance(val, float) else f"{val:,}" \
            if isinstance(val, int) else str(val)
        print(f"   {flag:<5} {name:<38} {shown:>16}")

    if bad:
        raise SystemExit(f"\n{len(bad)} miar niesprawnych.")
    print("\nModel semantyczny zweryfikowany.")


if __name__ == "__main__":
    main()
