"""Zapisuje semantic-model/MEASURES.md z definicji faktycznie wdrozonych.

Dokumentacja miar pisana recznie rozjezdza sie z modelem po pierwszej poprawce
formuly. Zrodlem prawdy jest modul opisujacy model, a ten plik tylko go
przepisuje do czytelnej postaci.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser(description="Generuje MEASURES.md z definicji modelu.")
ap.add_argument("--module", default="model_spec.py",
                help="Modul z slownikiem MEASURES (w katalogu deploy).")
ap.add_argument("--title", default="Miary DAX")
ap.add_argument("--model", required=True, help="Nazwa modelu semantycznego.")
args = ap.parse_args()

spec = importlib.util.spec_from_file_location("_spec", Path(__file__).with_name(args.module))
mod = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
spec.loader.exec_module(mod)

FORMAT_HELP = {
    "#,0": "liczba całkowita",
    "#,0.0": "liczba z jednym miejscem",
    "0.0%": "procent",
    "0.00": "wskaźnik 0–1",
}

lines = [f"# {args.title}", "",
         f"Miary modelu `{args.model}`, wygenerowane z `deploy/{args.module}`.",
         "Plik powstaje skryptem `deploy/export_measures.py` — nie edytuj go ręcznie,",
         "bo przy najbliższym wdrożeniu zmiany zostaną nadpisane.", ""]

total = 0
for table in sorted(mod.MEASURES):
    measures = mod.MEASURES[table]
    if not measures:
        continue
    lines += [f"## `{table}`", ""]
    for name, expr, fmt in measures:
        total += 1
        opis = FORMAT_HELP.get(fmt, "tekst" if fmt is None else fmt)
        lines += [f"### {name}", "", "```dax", f"{name} =", expr, "```", "",
                  f"Format: {opis}.", ""]

lines.insert(5, f"Łącznie {total} miar w {len([t for t in mod.MEASURES if mod.MEASURES[t]])} tabelach.")
lines.insert(6, "")

out = BASE / "semantic-model" / "MEASURES.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"zapisano {out} ({total} miar)")
