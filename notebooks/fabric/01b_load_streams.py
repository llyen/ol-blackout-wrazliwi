# CELL
# 📡 Ładowanie strumieni zdarzeń (JSONL) scenariusza „Tarcza Zimowa" do Lakehouse Delta

# CELL
from pyspark.sql import functions as F
from pyspark.sql import types as T

base = "Files/streams"

# Wolumeny strumieni:
#   telecom_coverage.jsonl  ~ 76 MB  (522 647 rekordów)
#   weather_readings.jsonl  ~ 32 MB  (201 020 rekordów)
# Dla Sparka to wartości komfortowe; przy wgrywaniu na One Lake przez skrypt
# wdrożeniowy nie wymaga podzialu na chunki.
streams = [
    "weather_readings",
    "outage_events",
    "telecom_coverage",
    "emergency_calls",
    "heating_point_status",
    "generator_dispatch",
    "welfare_check",
    "alert_delivery",
]

# Kolumny liczbowe, których Spark nie odczyta poprawnie ze struktury JSON
# gdy pole zostalo zapisane jako string (generatory danych Python).
numeric_columns = {
    "temperature_c": T.DoubleType(),
    "feels_like_c": T.DoubleType(),
    "wind_kmh": T.DoubleType(),
    "snow_cm_30m": T.DoubleType(),
    "icing_index": T.DoubleType(),
    "customers_without_power": T.LongType(),
    "cascade_stage": T.IntegerType(),
    "coverage_pct": T.DoubleType(),
    "bts_total": T.IntegerType(),
    "bts_on_battery": T.IntegerType(),
    "battery_hours_remaining": T.DoubleType(),
    "capacity": T.IntegerType(),
    "occupancy": T.IntegerType(),
    "power_kw": T.DoubleType(),
    "messages_sent": T.LongType(),
    "messages_delivered": T.LongType(),
    "messages_opened": T.LongType(),
}

# Pola logiczne w strumieniach — generowane jako "True"/"False" lub 1/0.
bool_columns = [
    "needs_food",
    "needs_generator",
    "needs_medical_support",
]

# Generator zapisuje czas w formacie ISO bez sekund (2026-01-14T12:12+02:00).
# Domyslny to_timestamp takiego zapisu nie rozpoznaje i zwraca null, co po cichu
# psulo cala warstwe analityczna - stad jawna lista wzorcow z fallbackiem.
def parse_event_time(column):
    return F.coalesce(
        F.to_timestamp(column, "yyyy-MM-dd'T'HH:mm:ssXXX"),
        F.to_timestamp(column, "yyyy-MM-dd'T'HH:mmXXX"),
        F.to_timestamp(column, "yyyy-MM-dd'T'HH:mm:ss"),
        F.to_timestamp(column, "yyyy-MM-dd'T'HH:mm"),
        F.to_timestamp(column),
    )

# CELL
for name in streams:
    df = spark.read.json(f"{base}/{name}.jsonl")

    for col, dtype in numeric_columns.items():
        if col in df.columns:
            df = df.withColumn(col, F.col(col).cast(dtype))

    for col in bool_columns:
        if col in df.columns:
            df = df.withColumn(col, (F.col(col).cast(T.StringType()) == "True").cast(T.BooleanType()))

    # Jednolity zapis czasu zdarzenia jako TimestampType.
    # Strumienie uzywaja kolumny event_time; eta_restore_time jest opcjonalne.
    if "event_time" in df.columns:
        df = df.withColumn("event_time", parse_event_time("event_time"))
    if "eta_restore_time" in df.columns:
        df = df.withColumn("eta_restore_time", parse_event_time("eta_restore_time"))

    df = df.withColumn("ingested_at", F.current_timestamp())

    df.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable(name)
    print(name, df.count(), "wierszy |", len(df.columns), "kolumn")

# CELL
# Kontrola zakresu sceny: D0 = 2026-01-15, awaria powinna trwac przez kolejne doby.
zakres = spark.sql("""
    SELECT
        min(event_time) AS od,
        max(event_time) AS do_,
        count(*) AS rekordy
    FROM outage_events
""").collect()[0]
print(f"outage_events: {zakres['od']} -> {zakres['do_']} ({zakres['rekordy']} rekordow)")

assert spark.table("outage_events").count() == 6650, "Oczekiwano 6650 zdarzeń awarii"
# Bez tej kontroli bledne parsowanie czasu przechodzi niezauwazone, a kolejne
# notatniki widza po prostu "brak awarii".
for tabela in streams:
    puste = spark.table(tabela).filter(F.col("event_time").isNull()).count()
    assert puste == 0, f"{tabela}: {puste} rekordow bez event_time - sprawdz wzorzec parsowania"
assert spark.table("weather_readings").count() > 0
assert spark.table("telecom_coverage").count() > 0
assert spark.table("alert_delivery").count() == 7431, "Oczekiwano 7431 alertów"

# Weryfikacja, ze coverage_pct jest liczbowy — Direct Lake potrzebuje float dla sredniej.
cov_type = dict(spark.table("telecom_coverage").dtypes)["coverage_pct"]
assert cov_type == "double", f"coverage_pct powinno byc double, jest: {cov_type}"

print("Strumienie zaladowane i zwalidowane.")
