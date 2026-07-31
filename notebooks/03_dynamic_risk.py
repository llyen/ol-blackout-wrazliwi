# CELL
from pathlib import Path
import json

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "datasets"
OUT = DATA / "derived"
OUT.mkdir(exist_ok=True)

# CELL
g = pd.read_csv(DATA / "dim_gmina.csv", dtype={"gmina_code": str, "powiat_code": str})
iwl = pd.read_csv(OUT / "iwl_by_gmina.csv", dtype={"gmina_code": str})[
    ["gmina_code", "iwl_score", "vulnerable_population_est", "rescue_travel_time_min"]
]
out = pd.read_json(DATA / "outage_events.jsonl", lines=True, dtype={"gmina_code": str})
tele = pd.read_json(DATA / "telecom_coverage.jsonl", lines=True, dtype={"gmina_code": str})
w = pd.read_json(DATA / "weather_readings.jsonl", lines=True, dtype={"powiat_code": str})
for df in [out, tele, w]:
    df["event_time"] = pd.to_datetime(df["event_time"], utc=True)

snapshot = pd.Timestamp("2026-01-16T18:00:00+02:00").tz_convert("UTC")
out_s = out[out.event_time <= snapshot]
tele_s = tele[tele.event_time <= snapshot]
w_s = w[w.event_time <= snapshot]
latest = out_s.sort_values("event_time").groupby("gmina_code").tail(1)
active = latest[latest.status != "restored"][["gmina_code", "event_time", "customers_without_power"]]
first = out_s.groupby("gmina_code").event_time.min().rename("outage_start").reset_index()
active = active.merge(first, on="gmina_code")
active["hours_without_power"] = ((snapshot - active.outage_start).dt.total_seconds() / 3600).clip(lower=0)
tele_latest = tele_s.sort_values("event_time").groupby("gmina_code").tail(1)[["gmina_code", "coverage_pct"]]
w_latest = w_s.sort_values("event_time").groupby("powiat_code").tail(1)[["powiat_code", "feels_like_c"]]
base = (
    g[["gmina_code", "powiat_code", "voivodeship_code", "gmina_name", "population"]]
    .merge(iwl, on="gmina_code")
    .merge(active, on="gmina_code", how="left")
    .merge(tele_latest, on="gmina_code", how="left")
    .merge(w_latest, on="powiat_code", how="left")
)
base[["customers_without_power", "hours_without_power"]] = base[["customers_without_power", "hours_without_power"]].fillna(0)
base["coverage_pct"] = base.coverage_pct.fillna(.9)
base["feels_like_c"] = base.feels_like_c.fillna(-8)
base["temp_component"] = ((-15 - base.feels_like_c).clip(lower=0) / 15).clip(upper=1)
base["outage_component"] = (base.hours_without_power / 72).clip(upper=1)
base["telecom_component"] = (1 - base.coverage_pct).clip(lower=0)
base["rescue_component"] = (base.rescue_travel_time_min / 75).clip(upper=1)
base["izz_score"] = (
    0.38 * (base.iwl_score / 100)
    + 0.30 * base.outage_component
    + 0.18 * base.temp_component
    + 0.09 * base.telecom_component
    + 0.05 * base.rescue_component
) * 100
base["izz_score"] = base.izz_score.round(2)
base["life_threat_level"] = pd.cut(base.izz_score, [-1, 40, 60, 75, 101], labels=["monitoring", "elevated", "high", "critical"])
base["vulnerable_without_power"] = (base.vulnerable_population_est * (base.customers_without_power / base.population).clip(0, 1)).round().astype(int)
crit = base[base.life_threat_level.astype(str) == "critical"].sort_values("izz_score", ascending=False)
base.sort_values("izz_score", ascending=False).to_csv(OUT / "dynamic_risk_latest.csv", index=False)
crit.to_csv(OUT / "critical_gminas_latest.csv", index=False)
cross = []
for _, row in crit.iterrows():
    static_part = (
        0.38 * (row.iwl_score / 100)
        + 0.18 * row.temp_component
        + 0.09 * row.telecom_component
        + 0.05 * row.rescue_component
    )
    needed_outage_component = max(0, (0.75 - static_part) / 0.30)
    hours_to_critical = min(row.hours_without_power, needed_outage_component * 72)
    crossing_time = row.outage_start + pd.to_timedelta(hours_to_critical, unit="h")
    cross.append({
        "gmina_code": row.gmina_code,
        "gmina_name": row.gmina_name,
        "first_critical_time": crossing_time.isoformat(),
        "izz_score_at_snapshot": row.izz_score,
        "main_drivers": "IWL + outage_hours + severe_cold + telecom_loss",
    })
pd.DataFrame(cross).to_csv(OUT / "critical_crossing_times.csv", index=False)
summary = {
    "critical_gminas": int(len(crit)),
    "vulnerable_without_power": int(base.vulnerable_without_power.sum()),
    "top_izz": round(float(base.izz_score.max()), 2),
    "max_hours_without_power": round(float(base.hours_without_power.max()), 1),
    "snapshot_time": snapshot.isoformat(),
}
(OUT / "dynamic_risk_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True))
