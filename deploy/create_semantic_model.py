"""Tworzy model semantyczny OL_BLK_SemanticModel (Direct Lake) w Microsoft Fabric.

Model jest wspólną warstwą dla raportu Power BI, Data Agenta i reguł Activatora —
opis w `semantic-model/MODEL.md`, miary w `semantic-model/MEASURES.md`.

Schematy tabel czytamy z `deploy/lakehouse_schemas.json` (zrzut z `get_schemas.py`),
a nie przepisujemy z dokumentacji: kolumny zmieniają się przy każdej zmianie
notatnika i ręczna lista rozjechałaby się po pierwszej takiej zmianie.
"""
import argparse
import base64
import json
import subprocess
import time
import uuid
from pathlib import Path

import requests

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

API = "https://api.fabric.microsoft.com/v1"
BASE = Path(__file__).resolve().parent.parent

_ap = argparse.ArgumentParser(description="Tworzy model semantyczny Direct Lake w Fabric.")
_ap.add_argument("--deployment", default=str(BASE / ".fabric" / "deployment.json"))
_ap.add_argument("--schemas", default=str(BASE / "deploy" / "lakehouse_schemas.json"))
_ap.add_argument("--name", default="OL_BLK_SemanticModel")
ARGS = _ap.parse_args()

CFG = json.load(open(ARGS.deployment, encoding="utf-8"))
WS = CFG["workspaceId"]
LAKEHOUSE = CFG["lakehouseName"]
SQL_EP = CFG["sqlEndpoint"]
NAME = ARGS.name

SCHEMAS = {t: [tuple(c) for c in cols]
           for t, cols in json.load(open(ARGS.schemas, encoding="utf-8")).items()}

DTYPE = {"string": "string", "integer": "int64", "long": "int64", "double": "double",
         "float": "double", "boolean": "boolean", "date": "dateTime", "timestamp": "dateTime"}

from model_spec import MEASURES, RELATIONSHIPS, HIDDEN_TABLES  # noqa: E402

NUMERIC = {"int64", "double"}


def lt() -> str:
    return str(uuid.uuid4())


def ind(text: str, n: int) -> str:
    pad = "\t" * n
    return "\n".join(pad + line if line else line for line in text.split("\n"))


def table_tmdl(name: str, cols) -> str:
    out = [f"table {name}", ""]
    if name in HIDDEN_TABLES:
        out += ["\tisHidden", ""]
    if name == "dim_date":
        out += ["\tdataCategory: Time", ""]
    for m_name, expr, fmt in MEASURES.get(name, []):
        if "\n" in expr:
            out.append(f"\tmeasure '{m_name}' =")
            out.append(ind(expr, 3))
        else:
            out.append(f"\tmeasure '{m_name}' = {expr}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append("\t\tdisplayFolder: _Miary")
        out.append(f"\t\tlineageTag: {lt()}")
        out.append("")
    for col, typ in cols:
        dt = DTYPE.get(typ, "string")
        out.append(f"\tcolumn {col}")
        out.append(f"\t\tdataType: {dt}")
        if dt in NUMERIC and name.startswith(("fact_", "dynamic_risk", "outage_", "alert_", "generator_")):
            out.append("\t\tsummarizeBy: sum")
        else:
            out.append("\t\tsummarizeBy: none")
        out.append(f"\t\tsourceColumn: {col}")
        if name == "dim_date" and col == "date":
            out.append("\t\tisKey")
        if dt == "dateTime":
            out.append("\t\tformatString: " + ("Long Date" if typ == "date" else "General Date"))
        if col == "ingested_at":
            out.append("\t\tisHidden")
        out.append(f"\t\tlineageTag: {lt()}")
        out.append("")
    out += [f"\tpartition {name} = entity", "\t\tmode: directLake", "\t\tsource",
            f"\t\t\tentityName: {name}", "\t\t\texpressionSource: DatabaseQuery", "",
            "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def model_tmdl() -> str:
    out = ["model Model", "\tculture: pl-PL", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
           "\tsourceQueryCulture: pl-PL", "\tdataAccessOptions", "\t\tlegacyRedirects",
           "\t\treturnErrorValuesAsNull", ""]
    out += [f"ref table {t}" for t in sorted(SCHEMAS)]
    out += ["", "ref cultureInfo pl-PL", ""]
    for rel in RELATIONSHIPS:
        f, fc, tt, tc = rel[:4]
        active = rel[4] if len(rel) > 4 else True
        out.append(f"relationship rel_{f}_{fc}_{tt}_{tc}")
        out.append(f"\tfromColumn: {tt}.{tc}")
        out.append(f"\ttoColumn: {f}.{fc}")
        if not active:
            out.append("\tisActive: false")
        out.append("")
    return "\n".join(out)


PBISM = {"version": "4.0", "settings": {"qnaEnabled": True}}
DATABASE = "database\n\tcompatibilityLevel: 1604\n"
EXPR = (f'expression DatabaseQuery =\n'
        f'\t\tlet\n'
        f'\t\t    database = Sql.Database("{SQL_EP}", "{LAKEHOUSE}")\n'
        f'\t\tin\n'
        f'\t\t    database\n'
        f'\tlineageTag: {lt()}\n'
        f'\tannotation PBI_IncludeFutureArtifacts = False\n')
CULTURE = ('cultureInfo pl-PL\n\tlinguisticMetadata =\n\t\t\t{\n\t\t\t  "Version": "1.0.0",\n'
           '\t\t\t  "Language": "pl-PL"\n\t\t\t}\n\t\tcontentType: json\n')


def build_parts():
    parts = {
        "definition.pbism": json.dumps(PBISM),
        "definition/database.tmdl": DATABASE,
        "definition/model.tmdl": model_tmdl(),
        "definition/expressions.tmdl": EXPR,
        "definition/cultures/pl-PL.tmdl": CULTURE,
    }
    for t, cols in SCHEMAS.items():
        parts[f"definition/tables/{t}.tmdl"] = table_tmdl(t, cols)
    return [{"path": p, "payload": base64.b64encode(c.encode("utf-8")).decode(),
             "payloadType": "InlineBase64"} for p, c in parts.items()]


def main() -> None:
    tok = subprocess.run(
        ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com",
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True).stdout.strip()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    items = requests.get(f"{API}/workspaces/{WS}/items?type=SemanticModel", headers=h).json()["value"]
    existing = next((i for i in items if i["displayName"] == NAME), None)
    definition = {"parts": build_parts()}
    if existing:
        r = requests.post(f"{API}/workspaces/{WS}/semanticModels/{existing['id']}/updateDefinition",
                          headers=h, json={"definition": definition})
        print("aktualizacja:", r.status_code, r.text[:1500])
        print("id:", existing["id"])
    else:
        r = requests.post(f"{API}/workspaces/{WS}/semanticModels", headers=h,
                          json={"displayName": NAME, "definition": definition})
        print("utworzenie:", r.status_code, r.text[:1500])
        if r.status_code == 202:
            loc = r.headers.get("Location")
            for _ in range(60):
                time.sleep(5)
                s = requests.get(loc, headers=h).json()
                if s.get("status") in ("Succeeded", "Failed"):
                    print(json.dumps(s, ensure_ascii=False)[:1500])
                    break


if __name__ == "__main__":
    main()
