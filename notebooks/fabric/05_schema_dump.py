# CELL
# 🧾 Zrzut schematów tabel Delta do OneLake — podstawa do budowy modelu semantycznego

# CELL
import json

# Schematy sa pomocne przy mapowaniu relacji w modelu semantycznym:
# Direct Lake wymaga znajomosci typow kolumn przed importem, a zgadywanie ich
# z CSV/JSONL prowadzi do bledow w miarach DAX i wizualizacjach map.
tables = sorted([t.name for t in spark.catalog.listTables()])
schema = {}
for name in tables:
    df = spark.table(name)
    schema[name] = {
        "rows": df.count(),
        "columns": [{"name": c, "type": t} for c, t in df.dtypes],
    }

payload = json.dumps(schema, ensure_ascii=False, indent=2)
mssparkutils.fs.put("Files/derived/lakehouse_schema.json", payload, True)

print(f"Tabel w Lakehouse: {len(schema)}")
for name, info in schema.items():
    col_summary = ", ".join(f"{c['name']}:{c['type']}" for c in info["columns"][:5])
    print(f"  {name:45s} {info['rows']:>8} wierszy | {col_summary} ...")
