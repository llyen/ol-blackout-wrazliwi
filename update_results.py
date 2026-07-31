from pathlib import Path
import json

BASE = Path(__file__).resolve().parent
DATA = BASE / "datasets"
OUT = DATA / "derived"


def load(name):
    p = OUT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def count_lines(p, header=False):
    with p.open(encoding="utf-8") as f:
        n = sum(1 for _ in f)
    return n - 1 if header else n


counts = {}
for p in DATA.glob("*.csv"):
    counts[p.name] = count_lines(p, True)
for p in DATA.glob("*.jsonl"):
    counts[p.name] = count_lines(p, False)

iwl = load("iwl_summary.json")
risk = load("dynamic_risk_summary.json")
opt = load("heating_point_optimization_summary.json")
welfare = load("welfare_check_summary.json")
whatif = load("whatif_summary.json")
block = f"""- Rekordy: {counts.get('dim_gmina.csv')} gmin, {counts.get('dim_powiat.csv')} powiatów, {counts.get('dim_care_facility.csv')} placówek opieki, {counts.get('dim_heating_point.csv')} punktów grzewczych, {counts.get('dim_generator_stock.csv')} agregatów, {counts.get('fact_priority_persons.csv')} fikcyjnych osób priorytetowych.
- Strumienie: pogoda {counts.get('weather_readings.jsonl')}, awarie {counts.get('outage_events.jsonl')}, łączność {counts.get('telecom_coverage.jsonl')}, zgłoszenia 112 {counts.get('emergency_calls.jsonl')}, status punktów {counts.get('heating_point_status.jsonl')}, wydania agregatów {counts.get('generator_dispatch.jsonl')}, wizyty {counts.get('welfare_check.jsonl')}, alerty {counts.get('alert_delivery.jsonl')}.
- IWL: średnia {iwl.get('avg_iwl')}, P90 {iwl.get('p90_iwl')}, top gmina {iwl.get('top_gmina')}.
- IZŻ: gminy krytyczne {risk.get('critical_gminas')}, osoby wrażliwe bez zasilania {risk.get('vulnerable_without_power')}, maks. czas bez prądu {risk.get('max_hours_without_power')} h.
- Optymalizacja: wybrano {opt.get('selected_points')} punktów, przydzielono {opt.get('generators_assigned')} agregatów; pokrycie {opt.get('optimized_coverage_pct')}% vs {opt.get('equal_distribution_coverage_pct')}% „po równo” (+{opt.get('improvement_pp')} p.p.).
- Wizyty: kolejka {welfare.get('priority_queue_size')} osób, pierwsza zmiana obsługuje {welfare.get('routed_visits_in_first_shift')} wizyt, zespoły {welfare.get('teams')}.
- What-if: gminy krytyczne rosną z {whatif.get('baseline_critical_gminas')} do {whatif.get('whatif_critical_gminas')} (+{whatif.get('additional_critical_gminas')})."""

for fname in ["README.md", "DEMO_SCRIPT.md"]:
    p = BASE / fname
    s = p.read_text(encoding="utf-8")
    a = s.index("<!-- RESULTS_START -->") + len("<!-- RESULTS_START -->")
    b = s.index("<!-- RESULTS_END -->")
    p.write_text(s[:a] + "\n" + block + "\n" + s[b:], encoding="utf-8")
print(block)
