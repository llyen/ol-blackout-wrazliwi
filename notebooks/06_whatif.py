# CELL
from pathlib import Path
import json

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "datasets"
OUT = DATA / "derived"

# CELL
risk = pd.read_csv(OUT / "dynamic_risk_latest.csv")
base_crit = int((risk.izz_score >= 75).sum())
risk["whatif_izz"] = (risk.izz_score + 7 * (risk.hours_without_power > 0) + 5 * ((-15 - risk.feels_like_c).clip(lower=0) / 15) + 4 * (risk.customers_without_power > 0)).clip(upper=100)
summary = {"baseline_critical_gminas": base_crit, "whatif_critical_gminas": int((risk.whatif_izz >= 75).sum()),
           "additional_critical_gminas": int((risk.whatif_izz >= 75).sum() - base_crit),
           "assumption": "awaria +12h, temperatura -5C, agregaty -30%"}
risk.sort_values("whatif_izz", ascending=False).to_csv(OUT / "whatif_extended_outage.csv", index=False)
(OUT / "whatif_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=True))
