# CELL
# 🔥 Dobór i optymalizacja punktów grzewczych — algorytm zachłanny z przydziałem agregatów

# CELL
import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql import types as T

# Dane sa niewielkie (500 kandydatów, 2477 gmin), wiec algorytm zachlanny dziala
# na pandas na driverze; Spark nie daje tu zysku obliczeniowego.
risk = spark.table("dynamic_risk_latest").select(
    "gmina_code", "vulnerable_without_power", "izz_score", "voivodeship_code"
).toPandas()
risk["gmina_code"] = risk["gmina_code"].astype(str)

hp = spark.table("dim_heating_point").toPandas()
hp["gmina_code"] = hp["gmina_code"].astype(str)

gens = spark.table("dim_generator_stock").toPandas()

gminas_geo = spark.table("dim_gmina").select("gmina_code", "lat", "lon").toPandas()
gminas_geo["gmina_code"] = gminas_geo["gmina_code"].astype(str)
gminas_geo["lat"] = gminas_geo["lat"].astype(float)
gminas_geo["lon"] = gminas_geo["lon"].astype(float)

# CELL
# 55% dostepnych agregatow rezerwujemy dla punktow bez wlasnego zasilania.
# Pozostale 45% idzie do placowek opieki i innego uzycia operacyjnego.
available_generators = int((gens["status"] == "available").sum() * 0.55)

candidates = hp[hp["availability_status"] != "unavailable"].copy()
risk_geo = risk[risk["vulnerable_without_power"] > 0].merge(gminas_geo, on="gmina_code", how="left")
risk_geo["need"] = risk_geo["vulnerable_without_power"]

def km_approx(lat1, lon1, lat2, lon2):
    """Przyblizenie odleglosci w km (bład < 3% dla odleglosci do 200 km w Polsce)."""
    return 111.0 * (((lat1 - lat2) ** 2 + ((lon1 - lon2) * 0.65) ** 2) ** 0.5)

# CELL
selected = []
covered = {}
remaining_generators = available_generators

# Punkt grzewczy przyjmuje gosci na rotacjach — 6 zmian dziennie, nie noclegi.
# Efektywna dzienna przepustowosc = capacity * 6.
ROTATIONS = 6
RADIUS_KM = 35

for _ in range(min(80, available_generators, len(candidates))):
    best, best_score = None, -1
    used_ids = {s["heating_point_id"] for s in selected}

    for _, p in candidates.iterrows():
        if p["heating_point_id"] in used_ids:
            continue

        p_lat, p_lon = float(p["lat"]), float(p["lon"])
        near = risk_geo.copy()
        near["dist_km"] = km_approx(p_lat, p_lon, near["lat"].astype(float), near["lon"].astype(float))
        near = near[near["dist_km"] <= RADIUS_KM]

        if near.empty:
            continue

        near["uncovered"] = near["gmina_code"].map(
            lambda gc: max(0, int(near.loc[near["gmina_code"] == gc, "need"].iloc[0]) - covered.get(gc, 0))
        )
        potential = int(near["uncovered"].sum())
        if potential <= 0:
            continue

        effective_capacity = int(p["capacity"]) * ROTATIONS

        # Punkt bez wlasnego zrodla zasilania potrzebuje agregatu — sprawdz dostepnosc.
        needs_generator = not bool(p["has_generator"] or p.get("has_independent_stove", False))
        if needs_generator and remaining_generators <= 0:
            continue

        # Koszt zasilania (power_need_kw) dyskontuje wynik proporcjonalnie,
        # zeby preferowac energooszczedne obiekty przy remisie pokrycia.
        score = min(potential, effective_capacity) / (1 + 0.02 * float(p["power_need_kw"]))
        if score > best_score:
            best, best_score = p, score

    if best is None:
        break

    needs_generator = not bool(best["has_generator"] or best.get("has_independent_stove", False))
    if needs_generator:
        remaining_generators -= 1

    effective_capacity = int(best["capacity"]) * ROTATIONS
    b_lat, b_lon = float(best["lat"]), float(best["lon"])
    near = risk_geo.copy()
    near["dist_km"] = km_approx(b_lat, b_lon, near["lat"].astype(float), near["lon"].astype(float))
    near = near[near["dist_km"] <= RADIUS_KM].copy()
    near["uncovered"] = near["gmina_code"].apply(
        lambda gc: max(0, int(near.loc[near["gmina_code"] == gc, "need"].iloc[0]) - covered.get(gc, 0))
    )
    near = near.sort_values(["izz_score", "uncovered"], ascending=[False, False])

    add = 0
    covered_gminas = []
    for _, r in near.iterrows():
        if add >= effective_capacity:
            break
        take = min(int(r["uncovered"]), effective_capacity - add)
        if take <= 0:
            continue
        covered[r["gmina_code"]] = covered.get(r["gmina_code"], 0) + take
        add += take
        covered_gminas.append(r["gmina_code"])

    selected.append({
        "heating_point_id": best["heating_point_id"],
        "gmina_code": best["gmina_code"],
        "capacity": int(best["capacity"]),
        "effective_daily_capacity": effective_capacity,
        "generator_assigned": bool(needs_generator),
        "covered_vulnerable_est": add,
        "covered_gminas": "|".join(covered_gminas[:8]),
        "score": round(best_score, 2),
    })

# CELL
sel = pd.DataFrame(selected)

sdf_sel = spark.createDataFrame(sel)
sdf_sel = sdf_sel.withColumn("generator_assigned", F.col("generator_assigned").cast(T.BooleanType())) \
                 .withColumn("snapshot_time", F.current_timestamp()) \
                 .withColumn("data_source", F.lit("heating_point_siting_greedy")) \
                 .withColumn("is_synthetic", F.lit(True))
sdf_sel.write.mode("overwrite").option("overwriteSchema", "true").format("delta").saveAsTable("selected_heating_points")

# CELL
total_need = int(risk["vulnerable_without_power"].sum())
opt_coverage = int(sel["covered_vulnerable_est"].sum()) if len(sel) else 0

# Wariant referencyjny „po równo": pierwsze N punktów wg kolejnosci w pliku,
# kazdy pracuje na pelna przepustowosc z 52% wykorzsytaniem (dane historyczne).
equal_hp = hp.head(len(sel))
equal_cov = int(min(total_need, equal_hp["capacity"].sum() * ROTATIONS * 0.52)) if len(equal_hp) else 0

assert len(sel) > 0, "Dobor nie zwrocil zadnych punktow — sprawdz dane risk i heating_point"
assert opt_coverage > equal_cov, "Optymalizacja powinna bic naiwny przydział"

print(
    f"Punkty: {len(sel)} | Agregaty: {int(sel['generator_assigned'].sum())}"
    f" | Pokrycie opt: {round(100*opt_coverage/total_need,1)}%"
    f" | Pokrycie rownomiernie: {round(100*equal_cov/total_need,1)}%"
    f" | Poprawa: +{round(100*(opt_coverage-equal_cov)/total_need,1)} p.p."
)
