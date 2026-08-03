# CELL
# 🌡️ Dynamiczny Wskaźnik Zagrożenia Życia (IZŻ) — przekrój ryzyka na moment snapshot

# CELL
import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql import types as T

# Snapshot demo: chwila, dla ktorej obliczamy biezacy stan zagrozen.
# Zmien na F.current_timestamp() lub parametr notatnika dla wdrozen produkcyjnych.
SNAPSHOT = "2026-01-16T16:00:00Z"

# CELL
# Agregacje strumieni wykonujemy w Sparku, zanim sciągniemy do pandas:
# telecom_coverage ma 522 k rekordow — kolekcja bez filtrowania byloby niezreczna.

outage_latest = spark.sql(f"""
    WITH ranked AS (
        SELECT *,
               row_number() OVER (PARTITION BY gmina_code ORDER BY event_time DESC) AS rn
        FROM outage_events
        WHERE event_time <= to_timestamp('{SNAPSHOT}')
    )
    SELECT gmina_code, event_time, customers_without_power, status
    FROM ranked WHERE rn = 1
""")

outage_first = spark.sql(f"""
    SELECT gmina_code, min(event_time) AS outage_start
    FROM outage_events
    WHERE event_time <= to_timestamp('{SNAPSHOT}')
    GROUP BY gmina_code
""")

# Aktywna awaria = ostatni status nie jest "restored".
active_outages = (
    outage_latest.filter(F.col("status") != "restored")
    .join(outage_first, "gmina_code")
    .withColumn(
        "hours_without_power",
        (F.unix_timestamp(F.to_timestamp(F.lit(SNAPSHOT))) - F.unix_timestamp("outage_start")) / 3600,
    )
    .withColumn("hours_without_power", F.greatest(F.col("hours_without_power"), F.lit(0.0)))
    .select("gmina_code", "event_time", "customers_without_power", "outage_start", "hours_without_power")
)

telecom_latest = spark.sql(f"""
    WITH ranked AS (
        SELECT *,
               row_number() OVER (PARTITION BY gmina_code ORDER BY event_time DESC) AS rn
        FROM telecom_coverage
        WHERE event_time <= to_timestamp('{SNAPSHOT}')
    )
    SELECT gmina_code, coverage_pct
    FROM ranked WHERE rn = 1
""")

weather_latest = spark.sql(f"""
    WITH ranked AS (
        SELECT *,
               row_number() OVER (PARTITION BY powiat_code ORDER BY event_time DESC) AS rn
        FROM weather_readings
        WHERE event_time <= to_timestamp('{SNAPSHOT}')
    )
    SELECT powiat_code, feels_like_c
    FROM ranked WHERE rn = 1
""")

# CELL
# Po agregacji Sparka rozmiare wynikowe sa male (rzedu gmin/powiatow),
# wiec dalsze obliczenia robimy w pandas — algorytm IZZ jest prostrzy do
# debugowania niz odpowiednik w DataFrame API.
gminas = spark.table("dim_gmina").select(
    "gmina_code", "powiat_code", "voivodeship_code", "gmina_name", "population"
).toPandas()
gminas["gmina_code"] = gminas["gmina_code"].astype(str)

iwl = spark.table("iwl_by_gmina").select(
    "gmina_code", "iwl_score", "vulnerable_population_est", "rescue_travel_time_min"
).toPandas()
iwl["gmina_code"] = iwl["gmina_code"].astype(str)

active_pd = active_outages.toPandas()
active_pd["gmina_code"] = active_pd["gmina_code"].astype(str)

telecom_pd = telecom_latest.toPandas()
telecom_pd["gmina_code"] = telecom_pd["gmina_code"].astype(str)

weather_pd = weather_latest.toPandas()
weather_pd["powiat_code"] = weather_pd["powiat_code"].astype(str)

# CELL
base = (
    gminas
    .merge(iwl, on="gmina_code")
    .merge(active_pd, on="gmina_code", how="left")
    .merge(telecom_pd, on="gmina_code", how="left")
    .merge(weather_pd, on="powiat_code", how="left")
)

base[["customers_without_power", "hours_without_power"]] = (
    base[["customers_without_power", "hours_without_power"]].fillna(0)
)
# Wartosci domyslne odzwierciedlają stan "normalny": pełne pokrycie sieci, łagodna temperatura.
base["coverage_pct"] = base["coverage_pct"].fillna(0.9)
base["feels_like_c"] = base["feels_like_c"].fillna(-8.0)

# Skladowe IZZ: kazda normalizowana do [0, 1] przed ważona suma.
# Progi dobrane tak, zeby scenariusz demo przy -15°C i 72h bez pradu dawał gminy krytyczne.
base["temp_component"] = ((-15 - base["feels_like_c"]).clip(lower=0) / 15).clip(upper=1)
base["outage_component"] = (base["hours_without_power"] / 72).clip(upper=1)
base["telecom_component"] = (1 - base["coverage_pct"]).clip(lower=0)
base["rescue_component"] = (base["rescue_travel_time_min"] / 75).clip(upper=1)

# Wagi IZZ: dominuje IWL (stan bazowy) + czas bez pradu (dynamiczny).
base["izz_score"] = (
    0.38 * (base["iwl_score"] / 100)
    + 0.30 * base["outage_component"]
    + 0.18 * base["temp_component"]
    + 0.09 * base["telecom_component"]
    + 0.05 * base["rescue_component"]
) * 100
base["izz_score"] = base["izz_score"].round(2)

base["life_threat_level"] = pd.cut(
    base["izz_score"], bins=[-1, 40, 60, 75, 101],
    labels=["monitoring", "elevated", "high", "critical"]
).astype(str)

# Szacunek osob wrazliwych bez zasilania proporcjonalnie do udzialu odbiorc bez pradu.
pop_safe = base["population"].clip(lower=1)
base["vulnerable_without_power"] = (
    base["vulnerable_population_est"]
    * (base["customers_without_power"] / pop_safe).clip(0, 1)
).round().astype(int)

base = base.sort_values("izz_score", ascending=False)

# CELL
def df_to_delta(pdf, table_name):
    sdf = spark.createDataFrame(pdf)
    sdf = sdf.withColumn("snapshot_time", F.to_timestamp(F.lit(SNAPSHOT))) \
             .withColumn("data_source", F.lit("dynamic_risk")) \
             .withColumn("is_synthetic", F.lit(True))
    sdf.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(table_name)
    return sdf.count()

cnt_risk = df_to_delta(base, "dynamic_risk_latest")

# Rozklad IZZ jest podstawa kalibracji progow - drukujemy go, bo od niego zalezy,
# czy scena ma w ogole gminy krytyczne.
print("IZZ opis:", base["izz_score"].describe().round(2).to_dict())
print("poziomy:", base["life_threat_level"].value_counts().to_dict())
print("max godz. bez pradu:", round(float(base["hours_without_power"].max()), 1),
      "| gmin z awaria:", int((base["hours_without_power"] > 0).sum()))

critical = base[base["life_threat_level"] == "critical"].copy()
cnt_crit = df_to_delta(critical, "critical_gminas_latest") if len(critical) else 0

# CELL
# Czas pierwszego przekroczenia progu krytycznego (IZZ >= 75) przez kazda gmine krytyczna.
# Obliczamy wstecznie: ile godzin awarii bylo potrzebnych przy danym stanie statycznym.
cross_rows = []
for _, row in critical.iterrows():
    static_part = (
        0.38 * (row["iwl_score"] / 100)
        + 0.18 * row["temp_component"]
        + 0.09 * row["telecom_component"]
        + 0.05 * row["rescue_component"]
    )
    # Minimalna wartosc outage_component, przy ktorej gmina przekracza prog 0.75.
    needed_outage = max(0.0, (0.75 - static_part) / 0.30)
    hours_to_critical = min(float(row["hours_without_power"]), needed_outage * 72)
    if pd.notna(row["outage_start"]):
        crossing = pd.to_datetime(row["outage_start"], utc=True) + pd.to_timedelta(hours_to_critical, unit="h")
        crossing_str = crossing.isoformat()
    else:
        crossing_str = None
    cross_rows.append({
        "gmina_code": row["gmina_code"],
        "gmina_name": row["gmina_name"],
        "first_critical_time": crossing_str,
        "izz_score_at_snapshot": row["izz_score"],
        "main_drivers": "IWL + outage_hours + severe_cold + telecom_loss",
    })

cross_df = pd.DataFrame(cross_rows)
if len(cross_df) == 0:
    print("UWAGA: brak gmin krytycznych - critical_crossing_times bedzie puste")
else:
    sdf_cross = spark.createDataFrame(cross_df)
    sdf_cross = sdf_cross.withColumn("snapshot_time", F.to_timestamp(F.lit(SNAPSHOT))) \
                         .withColumn("is_synthetic", F.lit(True))
    sdf_cross.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("critical_crossing_times")

# CELL
assert spark.table("dynamic_risk_latest").count() == 2477
assert cnt_crit > 0, "Brak gmin krytycznych - sprawdz snapshot i dane awarii"

summary = spark.sql("""
    SELECT
        count(*) AS gminy_krytyczne,
        sum(vulnerable_without_power) AS osoby_bez_zasilania,
        round(max(izz_score), 2) AS max_izz,
        round(max(hours_without_power), 1) AS max_godz_bez_pradu
    FROM dynamic_risk_latest
    WHERE life_threat_level = 'critical'
""").collect()[0]
print(
    f"Dynamiczne ryzyko | krytyczne={summary['gminy_krytyczne']}"
    f" | osoby_bez_zasilania={summary['osoby_bez_zasilania']}"
    f" | max_IZZ={summary['max_izz']}"
    f" | max_h={summary['max_godz_bez_pradu']}"
)
