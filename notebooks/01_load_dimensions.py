# CELL
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "datasets"

# CELL
for name in [
    "dim_voivodeship", "dim_powiat", "dim_gmina", "dim_vulnerability_factors",
    "fact_population_vulnerability", "dim_care_facility", "dim_heating_point", "dim_generator_stock",
]:
    df = pd.read_csv(DATA / f"{name}.csv")
    print(name, df.shape)
