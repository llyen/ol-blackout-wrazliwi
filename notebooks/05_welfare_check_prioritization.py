# CELL
from pathlib import Path
import json

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "datasets"
OUT = DATA / "derived"
OUT.mkdir(exist_ok=True)

# CELL
persons = pd.read_csv(DATA / "fact_priority_persons.csv", dtype={"gmina_code": str})
g = pd.read_csv(DATA / "dim_gmina.csv", dtype={"gmina_code": str})
risk = pd.read_csv(OUT / "dynamic_risk_latest.csv", dtype={"gmina_code": str})[["gmina_code", "izz_score", "coverage_pct", "hours_without_power"]]
df = persons.merge(risk, on="gmina_code", how="left").merge(g[["gmina_code", "lat", "lon", "voivodeship_code"]], on="gmina_code", how="left")
df[["izz_score", "hours_without_power"]] = df[["izz_score", "hours_without_power"]].fillna(0)
df["coverage_pct"] = df.coverage_pct.fillna(.9)
df["priority_score"] = (
    df.izz_score
    + (8 - df.medical_device_autonomy_hours).clip(lower=0) * 7
    + (df.age_band.eq("85+")) * 12
    + df.is_living_alone.astype(int) * 8
    + (1 - df.coverage_pct) * 25
).round(2)
queue = df.sort_values("priority_score", ascending=False).head(500).copy()
queue["queue_rank"] = range(1, len(queue) + 1)
queue[["queue_rank", "person_token", "category", "gmina_code", "priority_score", "medical_device_autonomy_hours",
       "age_band", "is_living_alone", "coverage_pct", "hours_without_power", "sensitivity_label"]].to_csv(OUT / "welfare_check_queue.csv", index=False)
routes = []
for team_no, (voiv, grp) in enumerate(queue.groupby("voivodeship_code"), 1):
    remaining = grp.head(80).copy()
    pos = (remaining.lat.mean(), remaining.lon.mean())
    elapsed, seq = 0, 1
    while len(remaining) and elapsed < 480:
        remaining["d"] = ((remaining.lat - pos[0]) ** 2 + (remaining.lon - pos[1]) ** 2) ** .5
        r = remaining.sort_values(["d", "priority_score"], ascending=[True, False]).iloc[0]
        travel = float(r.d) * 111 / 45 * 60
        if elapsed + travel + 18 > 480:
            break
        elapsed += travel + 18
        pos = (r.lat, r.lon)
        routes.append({"team_id": f"OSP-TEAM-{team_no:02d}", "sequence": seq, "person_token": r.person_token,
                       "gmina_code": r.gmina_code, "eta_min": round(elapsed, 1), "action": "visit_or_call_first_if_coverage_available"})
        remaining = remaining[remaining.person_token != r.person_token]
        seq += 1
pd.DataFrame(routes).to_csv(OUT / "welfare_check_routes.csv", index=False)
summary = {
    "priority_queue_size": int(len(queue)),
    "routed_visits_in_first_shift": int(len(routes)),
    "teams": int(queue.voivodeship_code.nunique()),
    "home_oxygen_in_top100": int((queue.head(100).category == "home_oxygen").sum()),
    "dialysis_in_top100": int((queue.head(100).category == "dialysis").sum()),
}
(OUT / "welfare_check_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True))
