# CELL
# 📥 Ładowanie wymiarów i rejestrów scenariusza „Tarcza Zimowa" do Lakehouse Delta

# CELL
from pyspark.sql import functions as F
from pyspark.sql import types as T

base = "Files/datasets"

# Tabele wymiarów i faktów bazowych wgrywane przed analizami.
# fact_priority_persons zawiera dane pseudonimizowane — RLS musi byc ustawiony
# w modelu semantycznym przed udostepnieniem raportu.
tables = [
    "dim_voivodeship",
    "dim_powiat",
    "dim_gmina",
    "dim_vulnerability_factors",
    "fact_population_vulnerability",
    "dim_care_facility",
    "dim_heating_point",
    "dim_generator_stock",
    "fact_priority_persons",
]

# Bez jawnego rzutowania Direct Lake widzi lat/lon jako tekst
# i wizualizacja mapy w Power BI odmawia dzialania.
# inferSchema pomija to na etapie planu zapytania, ale bywa niestabilny miedzy
# uruchomieniami — stad staly slownik typow.
numeric_columns = {
    "lat": T.DoubleType(),
    "lon": T.DoubleType(),
    "population": T.LongType(),
    "population_density": T.DoubleType(),
    "rurality_index": T.DoubleType(),
    "weight": T.DoubleType(),
    "capacity": T.IntegerType(),
    "current_occupancy": T.IntegerType(),
    "generator_autonomy_hours": T.DoubleType(),
    "power_need_kw": T.DoubleType(),
    "power_kw": T.DoubleType(),
    "medical_device_autonomy_hours": T.DoubleType(),
    "share_75_plus": T.DoubleType(),
    "single_senior_households": T.DoubleType(),
    "home_oxygen_patients": T.DoubleType(),
    "dialysis_patients": T.DoubleType(),
    "disability_share": T.DoubleType(),
    "care_facility_pressure": T.DoubleType(),
    "children_facilities": T.DoubleType(),
    "electric_heating_pct": T.DoubleType(),
    "no_alt_heat_buildings_pct": T.DoubleType(),
    "energy_poverty_pct": T.DoubleType(),
    "remote_rurality": T.DoubleType(),
    "telecom_gap_pct": T.DoubleType(),
    "rescue_travel_time_min": T.DoubleType(),
    "vulnerable_population_est": T.LongType(),
}

# CSV z generatora uzywa literalow "True"/"False" dla kolumn logicznych.
# Kast bezposrednio na BooleanType nie dziala dla stringa — konieczne porownanie.
bool_columns = [
    "has_generator",
    "has_independent_stove",
    "is_living_alone",
]

# CELL
for name in tables:
    df = spark.read.option("header", True).option("encoding", "UTF-8").csv(f"{base}/{name}.csv")

    for col, dtype in numeric_columns.items():
        if col in df.columns:
            df = df.withColumn(col, F.col(col).cast(dtype))

    for col in bool_columns:
        if col in df.columns:
            df = df.withColumn(col, (F.col(col) == "True").cast(T.BooleanType()))

    df = df.withColumn("ingested_at", F.current_timestamp())

    df.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(name)

    typy_kluczowe = {c: t for c, t in df.dtypes if c in {**numeric_columns, **{b: None for b in bool_columns}}}
    print(name, df.count(), "wierszy |", typy_kluczowe)

# CELL
assert spark.table("dim_voivodeship").count() == 16, "Oczekiwano 16 województw"
assert spark.table("dim_powiat").count() == 380, "Oczekiwano 380 powiatów"
assert spark.table("dim_gmina").count() == 2477, "Oczekiwano 2477 gmin"
assert spark.table("dim_gmina").filter(F.col("lat").isNull()).count() == 0, "lat nie moze byc NULL"
assert spark.table("dim_heating_point").count() == 500, "Oczekiwano 500 punktów grzewczych"
assert spark.table("dim_generator_stock").count() == 420, "Oczekiwano 420 agregatów"
assert spark.table("fact_priority_persons").count() == 1250, "Oczekiwano 1250 osób priorytetowych"

# Weryfikacja typów lat/lon — krytyczne dla Direct Lake i mapy Power BI
lat_type = dict(spark.table("dim_gmina").dtypes)["lat"]
assert lat_type == "double", f"dim_gmina.lat powinno byc double, jest: {lat_type}"

print("Wymiary zaladowane i zwalidowane.")
