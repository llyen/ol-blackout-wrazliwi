# CELL
from pathlib import Path
import json

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "datasets"
OUT = DATA / "derived"
OUT.mkdir(exist_ok=True)

# CELL
risk = pd.read_csv(OUT / "dynamic_risk_latest.csv", dtype={"gmina_code": str})
hp = pd.read_csv(DATA / "dim_heating_point.csv", dtype={"gmina_code": str})
gens = pd.read_csv(DATA / "dim_generator_stock.csv")
gminas = pd.read_csv(DATA / "dim_gmina.csv", dtype={"gmina_code": str})[["gmina_code", "lat", "lon"]]
risk["need"] = risk.vulnerable_without_power
candidates = hp[hp.availability_status != "unavailable"].copy()
available_generators = int((gens.status == "available").sum() * .55)
risk_geo = risk[risk.need > 0].merge(gminas, on="gmina_code", how="left").copy()
risk_idx = risk_geo.set_index("gmina_code")
selected, covered = [], {}
remaining_generators = available_generators
def km(lat1, lon1, lat2, lon2):
    return 111 * (((lat1 - lat2) ** 2 + ((lon1 - lon2) * .65) ** 2) ** .5)
for _ in range(min(80, available_generators, len(candidates))):
    best, best_score = None, -1
    used = {s["heating_point_id"] for s in selected}
    for _, p in candidates.iterrows():
        if p.heating_point_id in used:
            continue
        near = risk_geo[km(float(p.lat), float(p.lon), risk_geo.lat, risk_geo.lon) <= 35].copy()
        if near.empty:
            continue
        near["uncovered"] = near.apply(lambda r: max(0, int(r.need) - covered.get(r.gmina_code, 0)), axis=1)
        potential = int(near.uncovered.sum())
        if potential <= 0:
            continue
        effective_capacity = int(p.capacity) * 6  # 6 daily warming rotations, not overnight beds
        generator_needed = not bool(p.has_generator or p.has_independent_stove)
        if generator_needed and remaining_generators <= 0:
            continue
        score = min(potential, effective_capacity) / (1 + 0.02 * float(p.power_need_kw))
        if score > best_score:
            best, best_score = p, score
    if best is None:
        break
    gen_need = not bool(best.has_generator or best.has_independent_stove)
    if gen_need:
        remaining_generators -= 1
    effective_capacity = int(best.capacity) * 6
    near = risk_geo[km(float(best.lat), float(best.lon), risk_geo.lat, risk_geo.lon) <= 35].copy()
    near["uncovered"] = near.apply(lambda r: max(0, int(r.need) - covered.get(r.gmina_code, 0)), axis=1)
    near = near.sort_values(["izz_score", "uncovered"], ascending=[False, False])
    add = 0
    covered_gminas = []
    for _, r in near.iterrows():
        if add >= effective_capacity:
            break
        take = min(int(r.uncovered), effective_capacity - add)
        if take <= 0:
            continue
        covered[r.gmina_code] = covered.get(r.gmina_code, 0) + take
        add += take
        covered_gminas.append(r.gmina_code)
    selected.append({"heating_point_id": best.heating_point_id, "gmina_code": best.gmina_code, "capacity": int(best.capacity),
                     "effective_daily_capacity": effective_capacity, "generator_assigned": gen_need,
                     "covered_vulnerable_est": add, "covered_gminas": "|".join(covered_gminas[:8]), "score": round(best_score, 2)})
sel = pd.DataFrame(selected)
sel.to_csv(OUT / "selected_heating_points.csv", index=False)
total_need = int(risk.need.sum())
opt_cov = int(sel.covered_vulnerable_est.sum()) if len(sel) else 0
equal_hp = hp.head(len(sel))
equal_cov = int(min(total_need, equal_hp.capacity.sum() * 6 * .52)) if len(equal_hp) else 0
summary = {
    "selected_points": int(len(sel)),
    "generators_assigned": int(sel.generator_assigned.sum()) if len(sel) else 0,
    "total_vulnerable_need": total_need,
    "optimized_coverage": opt_cov,
    "optimized_coverage_pct": round(100 * opt_cov / total_need, 1) if total_need else 0,
    "equal_distribution_coverage": equal_cov,
    "equal_distribution_coverage_pct": round(100 * equal_cov / total_need, 1) if total_need else 0,
    "improvement_pp": round(100 * (opt_cov - equal_cov) / total_need, 1) if total_need else 0,
}
(OUT / "heating_point_optimization_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True))
