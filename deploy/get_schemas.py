"""Zrzuca schematy tabel Delta z Lakehouse do `deploy/lakehouse_schemas.json`.

Model semantyczny w trybie Direct Lake musi wymieniać kolumny co do nazwy i typu.
Zamiast przepisywać je ręcznie z dokumentacji — gdzie i tak by się rozjechały przy
pierwszej zmianie notatnika — czytamy pierwszy plik dziennika transakcji Delta
każdej tabeli i wyciągamy z niego schemat zapisany przez Sparka.
"""
import argparse
import json
import subprocess
from pathlib import Path

import requests

DFS = "https://onelake.dfs.fabric.microsoft.com"
BLOB = "https://onelake.blob.fabric.microsoft.com"
API = "https://api.fabric.microsoft.com/v1"
BASE = Path(__file__).resolve().parent.parent


def token(resource: str) -> str:
    return subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True).stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deployment", default=str(BASE / ".fabric" / "deployment.json"))
    ap.add_argument("--out", default=str(BASE / "deploy" / "lakehouse_schemas.json"))
    args = ap.parse_args()

    cfg = json.load(open(args.deployment, encoding="utf-8"))
    ws, lh = cfg["workspaceId"], cfg["lakehouseId"]

    storage = {"Authorization": f"Bearer {token('https://storage.azure.com')}",
               "x-ms-version": "2021-06-08"}
    fabric = {"Authorization": f"Bearer {token('https://api.fabric.microsoft.com')}"}

    tables = [t["name"] for t in requests.get(
        f"{API}/workspaces/{ws}/lakehouses/{lh}/tables", headers=fabric).json()["data"]]

    out: dict[str, list[list[str]]] = {}
    for table in sorted(tables):
        listing = requests.get(f"{DFS}/{ws}", headers=storage, params={
            "resource": "filesystem", "recursive": "true",
            "directory": f"{lh}/Tables/{table}/_delta_log"})
        if not listing.ok:
            print(f"{table}: blad listowania {listing.status_code}")
            continue
        logs = sorted(p["name"] for p in listing.json()["paths"] if p["name"].endswith(".json"))
        if not logs:
            print(f"{table}: brak dziennika transakcji")
            continue
        schema = None
        for line in requests.get(f"{BLOB}/{ws}/{logs[0]}", headers=storage).text.splitlines():
            entry = json.loads(line)
            if "metaData" in entry:
                schema = json.loads(entry["metaData"]["schemaString"])
        if schema:
            out[table] = [[f["name"], f["type"]] for f in schema["fields"]]
            print(f"{table}: {len(out[table])} kolumn")

    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print(f"zapisano {args.out} ({len(out)} tabel)")


if __name__ == "__main__":
    main()
