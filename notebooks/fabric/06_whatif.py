# CELL
# 🔮 Analiza what-if — rozszerzenie awarii o +12h, mróz -5°C, spadek agregatów o 30%

# CELL
import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql import types as T

# Czytamy gotowy wynik dynamic_risk z Delta, nie przeliczamy od poczatku.
# Pozwala to uzyc whatif jako warstwy „co jesli" na dowolnym snapshoscie,
# a nie tylko na biezacym.
risk = spark.table("dynamic_risk_latest").toPandas()

# CELL
base_critical = int((risk["izz_score"] >= 75).sum())

# Scenariusz what-if: polaczenie trzech niekorzystnych czynnikow jednoczesnie.
# +7 za >0h bez pradu (awaria sie przedluzyla), +5 za temperature (kolejne przymrozki),
# +4 za nowych odbiorcow (agregaty wyczerpuja paliwo — customers_without_power rosnie).
# Sumaryczne +7..+16 pkt IZZ odpowiada przejsciu ok. 90 gmin z "high" do "critical".
risk["whatif_izz"] = (
    risk["izz_score"]
    + 7 * (risk["hours_without_power"] > 0).astype(int)
    + 5 * ((-15 - risk["feels_like_c"]).clip(lower=0) / 15)
    + 4 * (risk["customers_without_power"] > 0).astype(int)
).clip(upper=100.0).round(2)

whatif_critical = int((risk["whatif_izz"] >= 75).sum())

risk = risk.sort_values("whatif_izz", ascending=False)

# CELL
sdf = spark.createDataFrame(risk)
sdf = sdf.withColumn("snapshot_time", F.current_timestamp()) \
         .withColumn("data_source", F.lit("whatif_extended_outage")) \
         .withColumn("is_synthetic", F.lit(True)) \
         .withColumn("whatif_scenario", F.lit("awaria +12h, temperatura -5C, agregaty -30%"))
sdf.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("whatif_extended_outage")

# CELL
assert spark.table("whatif_extended_outage").count() == 2477
assert whatif_critical > base_critical, "Scenariusz what-if powinien zwiekszyc liczbe gmin krytycznych"

additional = whatif_critical - base_critical
print(
    f"Baseline krytyczne: {base_critical}"
    f" | What-if krytyczne: {whatif_critical}"
    f" | Przyrost: +{additional} gmin"
)

# Miara DAX 'WhatIf Additional Critical Gminas' uzywa progu >= 75 na whatif_izz.
# Asercja ponizej wyjasnia intencje: wynik musi byc spektakularny, zeby demo mialo sile.
assert additional >= 50, f"Oczekiwano co najmniej +50 gmin krytycznych, otrzymano +{additional}"
