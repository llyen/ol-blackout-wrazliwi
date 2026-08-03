# CELL
# 🚑 Priorytetyzacja wizyt dobrostanowych (welfare check) i trasowanie zespołów OSP

# CELL
import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql import types as T

# fact_priority_persons zawiera dane pseudonimizowane (person_token zamiast danych osobowych).
# Model semantyczny wymaga RLS na tej tabeli (role OSP_Volunteer i MedicalCoordinator).
persons = spark.table("fact_priority_persons").toPandas()
persons["gmina_code"] = persons["gmina_code"].astype(str)

gminas_geo = spark.table("dim_gmina").select(
    "gmina_code", "lat", "lon", "voivodeship_code"
).toPandas()
gminas_geo["gmina_code"] = gminas_geo["gmina_code"].astype(str)
gminas_geo["lat"] = gminas_geo["lat"].astype(float)
gminas_geo["lon"] = gminas_geo["lon"].astype(float)

risk = spark.table("dynamic_risk_latest").select(
    "gmina_code", "izz_score", "coverage_pct", "hours_without_power"
).toPandas()
risk["gmina_code"] = risk["gmina_code"].astype(str)

# CELL
df = (
    persons
    .merge(risk, on="gmina_code", how="left")
    .merge(gminas_geo, on="gmina_code", how="left")
)
df[["izz_score", "hours_without_power"]] = df[["izz_score", "hours_without_power"]].fillna(0)
df["coverage_pct"] = df["coverage_pct"].fillna(0.9)
df["is_living_alone"] = df["is_living_alone"].fillna(False).astype(bool)

# Wzor priorytetu: IZZ gminy jest podstawa, modyfikowana przez stan osoby.
# Niski bufor autonomii urzadzenia medycznego (< 8h) silnie winduje priorytet,
# bo ryzyko smierci jest tu bezposrednie. Brak kontaktu telefonicznego (niska coverage_pct)
# wymaga fizycznej wizyty, wiec tez podwyzszamy rang.
df["medical_device_autonomy_hours"] = df["medical_device_autonomy_hours"].fillna(99.0).astype(float)

df["priority_score"] = (
    df["izz_score"]
    + (8 - df["medical_device_autonomy_hours"]).clip(lower=0) * 7
    + df["age_band"].eq("85+").astype(int) * 12
    + df["is_living_alone"].astype(int) * 8
    + (1 - df["coverage_pct"]) * 25
).round(2)

queue = df.sort_values("priority_score", ascending=False).head(500).copy()
queue["queue_rank"] = range(1, len(queue) + 1)

# CELL
queue_cols = [
    "queue_rank", "person_token", "category", "gmina_code",
    "priority_score", "medical_device_autonomy_hours",
    "age_band", "is_living_alone", "coverage_pct",
    "hours_without_power", "sensitivity_label",
]
sdf_queue = spark.createDataFrame(queue[queue_cols])
sdf_queue = sdf_queue.withColumn("snapshot_time", F.current_timestamp()) \
                     .withColumn("data_source", F.lit("welfare_check_prioritization")) \
                     .withColumn("is_synthetic", F.lit(True))
sdf_queue.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("welfare_check_queue")

# CELL
# Trasowanie: jeden zespol OSP per województwo, zmiana do 480 minut.
# Algorytm najbliższego sasiada z kryterium priorytetu przy remisie odleglosci.
# Koszt wizyty: dojazd + 18 minut na miejscu (standard OSP w scenariuszu).
SHIFT_MINUTES = 480
VISIT_MINUTES = 18
SPEED_KMH = 45

routes = []
for team_no, (voiv, grp) in enumerate(queue.groupby("voivodeship_code"), 1):
    remaining = grp.head(80).dropna(subset=["lat", "lon"]).copy()
    pos_lat = float(remaining["lat"].mean())
    pos_lon = float(remaining["lon"].mean())
    elapsed = 0.0
    seq = 1

    while len(remaining) > 0 and elapsed < SHIFT_MINUTES:
        remaining["d"] = (
            (remaining["lat"].astype(float) - pos_lat) ** 2
            + (remaining["lon"].astype(float) - pos_lon) ** 2
        ) ** 0.5

        r = remaining.sort_values(
            ["d", "priority_score"], ascending=[True, False]
        ).iloc[0]

        travel_min = float(r["d"]) * 111.0 / SPEED_KMH * 60.0
        if elapsed + travel_min + VISIT_MINUTES > SHIFT_MINUTES:
            break

        elapsed += travel_min + VISIT_MINUTES
        pos_lat, pos_lon = float(r["lat"]), float(r["lon"])

        routes.append({
            "team_id": f"OSP-TEAM-{team_no:02d}",
            "sequence": seq,
            "person_token": r["person_token"],
            "gmina_code": r["gmina_code"],
            "eta_min": round(elapsed, 1),
            "action": "visit_or_call_first_if_coverage_available",
        })
        remaining = remaining[remaining["person_token"] != r["person_token"]]
        seq += 1

routes_df = pd.DataFrame(routes)
sdf_routes = spark.createDataFrame(routes_df)
sdf_routes = sdf_routes.withColumn("snapshot_time", F.current_timestamp()) \
                       .withColumn("is_synthetic", F.lit(True))
sdf_routes.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("welfare_check_routes")

# CELL
assert spark.table("welfare_check_queue").count() == 500, "Kolejka powinna miec 500 osob"
assert spark.table("welfare_check_routes").count() > 0, "Brak zaplanowanych tras"

home_oxygen_top100 = int((queue.head(100)["category"] == "home_oxygen").sum())
dialysis_top100 = int((queue.head(100)["category"] == "dialysis").sum())
teams = int(queue["voivodeship_code"].nunique())

print(
    f"Kolejka: {len(queue)} | Trasy: {len(routes_df)} wizyt"
    f" | Zespoly: {teams}"
    f" | Top100: {home_oxygen_top100} tlenoterapii, {dialysis_top100} dializowanych"
)
