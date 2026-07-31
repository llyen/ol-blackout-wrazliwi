"""Generate deterministic synthetic data for BLACKOUT / ZIMA demo.

All data is fictional. Seed=42, UTF-8, synthetic TERYT-like codes.
"""
from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

SEED = 42
random.seed(SEED)
rng = np.random.default_rng(SEED)
BASE = Path(__file__).resolve().parent
DATA = BASE / "datasets"
DERIVED = DATA / "derived"
DATA.mkdir(exist_ok=True)
DERIVED.mkdir(exist_ok=True)
TZ = timezone(timedelta(hours=2))
START = datetime(2026, 1, 12, 0, 0, tzinfo=TZ)
D0 = datetime(2026, 1, 14, 6, 0, tzinfo=TZ)
END = datetime(2026, 1, 23, 0, 0, tzinfo=TZ)
TARGET = {"20", "28", "14", "06"}


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def write_csv(name: str, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or list(rows[0].keys())
    with (DATA / name).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(name: str, rows) -> None:
    with (DATA / name).open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


voivs = [
    ("02", "dolnośląskie", 51.1, 16.9), ("04", "kujawsko-pomorskie", 53.0, 18.5),
    ("06", "lubelskie", 51.2, 22.6), ("08", "lubuskie", 52.2, 15.5),
    ("10", "łódzkie", 51.8, 19.5), ("12", "małopolskie", 50.1, 19.9),
    ("14", "mazowieckie", 52.2, 21.0), ("16", "opolskie", 50.7, 17.9),
    ("18", "podkarpackie", 50.0, 22.0), ("20", "podlaskie", 53.1, 23.2),
    ("22", "pomorskie", 54.4, 18.6), ("24", "śląskie", 50.3, 19.0),
    ("26", "świętokrzyskie", 50.9, 20.6), ("28", "warmińsko-mazurskie", 53.8, 20.5),
    ("30", "wielkopolskie", 52.4, 16.9), ("32", "zachodniopomorskie", 53.4, 14.6),
]
voiv_rows = [
    {"voivodeship_code": c, "voivodeship_name": n, "lat": lat, "lon": lon,
     "scenario_axis": "MROZ_STYCZEN" if c in TARGET else "national_context"}
    for c, n, lat, lon in voivs
]
write_csv("dim_voivodeship.csv", voiv_rows)

pow_counts = {"02": 30, "04": 23, "06": 24, "08": 14, "10": 24, "12": 22, "14": 42, "16": 12,
              "18": 25, "20": 17, "22": 20, "24": 36, "26": 14, "28": 21, "30": 35, "32": 21}
powiats = []
for c, n, lat, lon in voivs:
    for i in range(1, pow_counts[c] + 1):
        suffix = ["północny", "południowy", "wschodni", "zachodni", "centralny", "miejski"][i % 6]
        powiats.append({"powiat_code": f"{c}{i:02d}", "voivodeship_code": c,
                        "powiat_name": f"powiat {n}-{suffix}-{i:02d}",
                        "lat": round(lat + rng.normal(0, .38), 5),
                        "lon": round(lon + rng.normal(0, .55), 5)})
write_csv("dim_powiat.csv", powiats)

extra = 2477 - 6 * len(powiats)
gminas = []
for p_idx, p in enumerate(powiats):
    for j in range(1, 7 + (1 if p_idx < extra else 0)):
        typ = random.choices(["miejska", "miejsko-wiejska", "wiejska"], [.18, .26, .56])[0]
        rural = 1 if typ == "wiejska" else .45 if typ == "miejsko-wiejska" else .08
        pop = int(clamp(rng.lognormal(9.0 if typ != "miejska" else 10.2, .62), 1800, 240000))
        dens = round(clamp((pop / rng.uniform(45, 260)) * (1.7 if typ == "miejska" else .55 if typ == "wiejska" else .9), 12, 3200), 1)
        code = f"{p['powiat_code']}{j:03d}"[:7]
        gminas.append({"gmina_code": code, "powiat_code": p["powiat_code"],
                       "voivodeship_code": p["voivodeship_code"],
                       "gmina_name": f"gmina {p['powiat_name'].replace('powiat ', '')}-{j:02d}",
                       "gmina_type": typ, "population": pop, "population_density": dens,
                       "lat": round(float(p["lat"]) + rng.normal(0, .12), 5),
                       "lon": round(float(p["lon"]) + rng.normal(0, .18), 5),
                       "rurality_index": round(rural, 2)})
write_csv("dim_gmina.csv", gminas)
g_by = {g["gmina_code"]: g for g in gminas}
target_gminas = [g for g in gminas if g["voivodeship_code"] in TARGET]

factors = [
    ("share_75_plus", .10, "Odsetek ludności 75+"), ("single_senior_households", .10, "Samotne gospodarstwa seniorów"),
    ("home_oxygen_patients", .12, "Pacjenci tlenoterapii domowej"), ("dialysis_patients", .09, "Pacjenci dializowani"),
    ("disability_share", .08, "Osoby z niepełnosprawnością"), ("care_facility_pressure", .08, "DPS/ZOL/hospicja"),
    ("children_facilities", .04, "Żłobki i przedszkola"), ("electric_heating_pct", .11, "Ogrzewanie elektryczne"),
    ("no_alt_heat_buildings_pct", .09, "Brak alternatywnego ciepła"), ("energy_poverty_pct", .08, "Ubóstwo energetyczne"),
    ("remote_rurality", .06, "Oddalenie obszarów wiejskich"), ("telecom_gap_pct", .08, "Brak zasięgu"),
    ("rescue_travel_time_min", .07, "Czas dojazdu ratownictwa"),
]
write_csv("dim_vulnerability_factors.csv",
          [{"factor_code": c, "weight": w, "description": d, "normalization": "min_max_0_1"} for c, w, d in factors])

vuln = []
for g in gminas:
    rural = float(g["rurality_index"])
    incident = 1 if g["voivodeship_code"] in TARGET else 0
    north = 1 if g["voivodeship_code"] in {"20", "28"} else 0
    pop = int(g["population"])
    r = {
        "gmina_code": g["gmina_code"], "population": pop,
        "share_75_plus": round(clamp(rng.normal(.105 + .035 * rural + .015 * north, .025), .045, .24), 4),
        "single_senior_households": round(clamp(rng.normal(.055 + .03 * rural, .018), .015, .16), 4),
        "home_oxygen_patients": int(clamp(rng.poisson(pop / 1850 * (1 + .25 * rural)), 0, 180)),
        "dialysis_patients": int(clamp(rng.poisson(pop / 4800), 0, 80)),
        "disability_share": round(clamp(rng.normal(.105 + .025 * rural, .025), .04, .22), 4),
        "care_facility_pressure": round(clamp(rng.normal(.25 + .08 * (pop > 30000), .18), 0, 1), 4),
        "children_facilities": int(max(0, rng.poisson(pop / 3800))),
        "electric_heating_pct": round(clamp(rng.normal(.11 + .07 * incident + .05 * rural, .045), .02, .42), 4),
        "no_alt_heat_buildings_pct": round(clamp(rng.normal(.16 + .11 * incident + .08 * rural, .06), .03, .55), 4),
        "energy_poverty_pct": round(clamp(rng.normal(.085 + .045 * rural + .025 * incident, .035), .015, .28), 4),
        "remote_rurality": round(clamp(rural + rng.normal(0, .12), 0, 1), 4),
        "telecom_gap_pct": round(clamp(rng.normal(.08 + .11 * rural + .05 * incident, .05), 0, .45), 4),
        "rescue_travel_time_min": round(clamp(rng.normal(14 + 24 * rural + 6 * incident, 7), 5, 75), 1),
    }
    r["vulnerable_population_est"] = int(pop * (r["share_75_plus"] * .55 + r["disability_share"] * .35 + r["energy_poverty_pct"] * .4)
                                       + r["home_oxygen_patients"] + r["dialysis_patients"])
    vuln.append(r)
write_csv("fact_population_vulnerability.csv", vuln)
v_by = {v["gmina_code"]: v for v in vuln}

fac = []
for i, g in enumerate(random.choices(gminas, weights=[int(x["population"]) ** .6 for x in gminas], k=900), 1):
    ft = random.choices(["DPS", "ZOL", "hospital", "hospice", "night_shelter", "homeless_shelter"], [.28, .13, .20, .08, .16, .15])[0]
    cap = int(clamp(rng.normal({"hospital": 180, "DPS": 95, "ZOL": 70, "hospice": 35, "night_shelter": 55, "homeless_shelter": 75}[ft], 25), 12, 520))
    has = random.random() < {"hospital": .92, "DPS": .55, "ZOL": .48, "hospice": .40, "night_shelter": .22, "homeless_shelter": .25}[ft]
    fac.append({"facility_id": f"FAC-{i:04d}", "facility_type": ft, "facility_name": f"{ft} {i:04d}",
                "gmina_code": g["gmina_code"], "capacity": cap, "current_occupancy": int(cap * rng.uniform(.62, .98)),
                "has_generator": has, "generator_autonomy_hours": round(rng.uniform(1, 18) if has else 0, 1),
                "power_need_kw": round(cap * rng.uniform(.35, 1.15), 1),
                "lat": round(float(g["lat"]) + rng.normal(0, .025), 5), "lon": round(float(g["lon"]) + rng.normal(0, .035), 5),
                "sensitivity_label": "Confidential - synthetic health/care aggregate"})
write_csv("dim_care_facility.csv", fac)

hps = []
for i, g in enumerate(random.sample(gminas, 500), 1):
    typ = random.choice(["school", "OSP_station", "community_hall", "sports_hall", "culture_center"])
    cap = int(clamp(rng.normal({"school": 180, "OSP_station": 80, "community_hall": 110, "sports_hall": 320, "culture_center": 140}[typ], 45), 35, 650))
    hps.append({"heating_point_id": f"HP-{i:04d}", "heating_point_type": typ, "gmina_code": g["gmina_code"],
                "capacity": cap, "has_generator": random.random() < .34, "has_independent_stove": random.random() < .45,
                "availability_status": "available" if random.random() < .83 else "needs_staff",
                "power_need_kw": round(cap * rng.uniform(.08, .22), 1),
                "lat": round(float(g["lat"]) + rng.normal(0, .018), 5), "lon": round(float(g["lon"]) + rng.normal(0, .028), 5)})
write_csv("dim_heating_point.csv", hps)

assets = []
asset_types = ["GPZ", "line_110kV", "MV_line", "transformer"]
for i in range(1, 601):
    g = random.choice(gminas)
    at = random.choices(asset_types, [.10, .18, .42, .30])[0]
    near = [x["gmina_code"] for x in random.sample(gminas, {"GPZ": 8, "line_110kV": 14, "MV_line": 5, "transformer": 2}[at])]
    if g["gmina_code"] not in near:
        near[0] = g["gmina_code"]
    assets.append({"grid_asset_id": f"GRID-{i:04d}", "asset_type": at, "operator_region": g["voivodeship_code"],
                   "primary_gmina_code": g["gmina_code"], "served_gminas": "|".join(near),
                   "customers_served": sum(int(g_by[c]["population"] * rng.uniform(.18, .72)) for c in near),
                   "lat": g["lat"], "lon": g["lon"],
                   "icing_susceptibility": round(clamp(rng.normal(.42 + (.25 if g["voivodeship_code"] in TARGET else 0), .18), 0, 1), 3)})
write_csv("dim_grid_asset.csv", assets)

warehouses = [("RCB-WAW", "14", 52.23, 21.01), ("MSW-BIA", "20", 53.13, 23.16), ("RARS-LUB", "06", 51.25, 22.57), ("RARS-OLS", "28", 53.78, 20.48), ("RARS-POZ", "30", 52.41, 16.93)]
gens = []
for i in range(1, 421):
    wh = random.choice(warehouses)
    kw = random.choice([8, 12, 20, 30, 50, 80, 120, 200])
    gens.append({"generator_id": f"GEN-{i:04d}", "warehouse_id": wh[0], "voivodeship_code": wh[1], "power_kw": kw,
                 "fuel_type": random.choice(["diesel", "petrol", "LPG"]), "mobility_type": "trailer" if kw >= 20 and random.random() < .75 else "portable",
                 "status": random.choices(["available", "reserved", "maintenance"], [.72, .18, .10])[0], "lat": wh[2], "lon": wh[3]})
write_csv("dim_generator_stock.csv", gens)

persons = []
for i, g in enumerate(random.choices(gminas, weights=[v_by[x["gmina_code"]]["vulnerable_population_est"] + 50 for x in gminas], k=1250), 1):
    cat = random.choices(["home_oxygen", "dialysis", "senior_alone_85_plus"], [.24, .18, .58])[0]
    age = int(clamp(rng.normal(78 if cat != "senior_alone_85_plus" else 88, 7), 45, 101))
    autonomy = round({"home_oxygen": rng.uniform(1, 8), "dialysis": rng.uniform(4, 18), "senior_alone_85_plus": rng.uniform(8, 36)}[cat], 1)
    persons.append({"person_token": f"PRIO-{i:05d}", "category": cat, "gmina_code": g["gmina_code"],
                    "age_band": "85+" if age >= 85 else "75-84" if age >= 75 else "18-74",
                    "medical_device_autonomy_hours": autonomy, "fictional_contact": f"+48-000-{i//1000:03d}-{i%1000:03d}",
                    "is_living_alone": cat == "senior_alone_85_plus" or random.random() < .35,
                    "sensitivity_label": "Highly Confidential - synthetic priority person",
                    "privacy_note": "FIKCYJNE dane demo; w realnym wdrożeniu Purview/RLS/minimalizacja/retencja"})
write_csv("fact_priority_persons.csv", persons)

weather = []
t = START
while t <= END:
    hours = (t - D0).total_seconds() / 3600
    for p in powiats:
        incident = 1 if p["voivodeship_code"] in TARGET else 0
        temp = -8 - 8 * incident - 3 * math.exp(-((hours - 30) / 50) ** 2) + 3 * math.sin((t.hour / 24) * 2 * math.pi) + rng.normal(0, 1.2)
        wind = clamp(rng.normal(22 + 9 * incident, 8), 2, 65)
        snow = clamp(rng.gamma(1.2, .35) * (1 + incident), 0, 5.5)
        weather.append({"event_time": iso(t), "powiat_code": p["powiat_code"], "temperature_c": round(temp, 1),
                        "feels_like_c": round(temp - .12 * wind, 1), "wind_kmh": round(wind, 1),
                        "snow_cm_30m": round(snow, 2), "icing_index": round(clamp((snow / 5) + (.35 if temp < -8 else 0) + rng.normal(0, .08), 0, 1), 3)})
    t += timedelta(minutes=30)
write_jsonl("weather_readings.jsonl", weather)

critical_pool = sorted(target_gminas, key=lambda g: v_by[g["gmina_code"]]["vulnerable_population_est"], reverse=True)[:180]
affected = random.sample(critical_pool, 150) + random.sample([g for g in target_gminas if g not in critical_pool], 110)
affected_codes = {g["gmina_code"] for g in affected}
outages = []
for idx, g in enumerate(affected):
    start = D0 + timedelta(hours=rng.uniform(0, 18) + (0 if idx < 80 else rng.uniform(8, 36)))
    duration = float(clamp(rng.normal(55 if g["voivodeship_code"] in {"20", "28"} else 38, 16), 10, 120))
    asset = random.choice([a for a in assets if a["operator_region"] == g["voivodeship_code"]])
    step = 0
    while True:
        tt = start + timedelta(hours=2 * step)
        if tt > END or tt > start + timedelta(hours=duration + 4):
            break
        elapsed = (tt - start).total_seconds() / 3600
        status = "outage" if elapsed < duration * .7 else "partial_restoration" if elapsed < duration else "restored"
        cust = int(int(g["population"]) * clamp(rng.normal(.72 if status == "outage" else .28 if status == "partial_restoration" else .03, .08), 0, 1))
        outages.append({"event_time": iso(tt), "outage_id": f"OUT-{idx + 1:04d}", "grid_asset_id": asset["grid_asset_id"],
                        "gmina_code": g["gmina_code"], "status": status, "customers_without_power": cust,
                        "eta_restore_time": iso(start + timedelta(hours=duration)),
                        "cascade_stage": 1 if idx < 70 else 2 if idx < 170 else 3, "root_cause": "icing_cascade_overload"})
        step += 1
write_jsonl("outage_events.jsonl", outages)

tele = []
t = D0
while t <= END:
    for g in gminas:
        aff = g["gmina_code"] in affected_codes
        outage_age = max(0, (t - D0).total_seconds() / 3600) if aff else 0
        battery = 4 + (hash(g["gmina_code"]) % 5)
        base = .93 - v_by[g["gmina_code"]]["telecom_gap_pct"]
        if aff and outage_age > battery:
            base -= clamp((outage_age - battery) / 24 * .75, 0, .78)
        tele.append({"event_time": iso(t), "gmina_code": g["gmina_code"],
                     "bts_total": int(clamp(rng.normal(5 + int(g["population"]) / 18000, 2), 1, 45)),
                     "bts_on_battery": (random.randint(1, 4) if aff and outage_age < battery else 0),
                     "coverage_pct": round(clamp(base + rng.normal(0, .03), .03, .99), 3),
                     "battery_hours_remaining": round(max(0, battery - outage_age), 1) if aff else ""})
    t += timedelta(hours=1)
write_jsonl("telecom_coverage.jsonl", tele)

calls = []
call_id = 1
for h in range(0, int((END - START).total_seconds() / 3600) + 1):
    t = START + timedelta(hours=h)
    incident_hours = max(0, (t - D0).total_seconds() / 3600)
    for g in random.sample(gminas, 380):
        aff = g["gmina_code"] in affected_codes
        lam = (.006 + .03 * aff + .0012 * incident_hours * aff) * (int(g["population"]) / 10000) * (1 + v_by[g["gmina_code"]]["share_75_plus"] * 3)
        for _ in range(int(rng.poisson(lam))):
            typ = random.choices(["hypothermia", "no_heating", "medical_device_failure", "trapped_vehicle", "welfare_check_request"], [.18, .34, .22, .10, .16])[0]
            calls.append({"event_time": iso(t + timedelta(minutes=random.randint(0, 59))), "call_id": f"112-{call_id:06d}",
                          "gmina_code": g["gmina_code"], "call_type": typ,
                          "priority": random.choices(["P1", "P2", "P3"], [.22 if typ in {"hypothermia", "medical_device_failure"} else .08, .52, .26])[0],
                          "description": "synthetic emergency call - no personal data"})
            call_id += 1
write_jsonl("emergency_calls.jsonl", calls)

hp_status = []
for hp in hps:
    if hp["gmina_code"] in affected_codes and random.random() < .72:
        start = D0 + timedelta(hours=rng.uniform(5, 34))
        for k in range(0, 40, 4):
            occ = int(clamp(rng.normal(float(hp["capacity"]) * (.3 + k / 80), 25), 0, float(hp["capacity"]) * 1.08))
            hp_status.append({"event_time": iso(start + timedelta(hours=k)), "heating_point_id": hp["heating_point_id"],
                              "gmina_code": hp["gmina_code"], "status": "open", "occupancy": occ,
                              "capacity": hp["capacity"], "needs_food": occ > hp["capacity"] * .55,
                              "needs_medical_support": occ > hp["capacity"] * .75, "needs_generator": not hp["has_generator"]})
write_jsonl("heating_point_status.jsonl", hp_status)

gdisp = []
for i, (gen, g) in enumerate(zip([x for x in gens if x["status"] == "available"][:260], affected), 1):
    gdisp.append({"event_time": iso(D0 + timedelta(hours=rng.uniform(8, 60))), "dispatch_id": f"DISP-{i:04d}",
                  "generator_id": gen["generator_id"], "target_type": random.choice(["heating_point", "care_facility", "water_utility", "gmina_command_post"]),
                  "gmina_code": g["gmina_code"], "status": random.choices(["planned", "in_transit", "deployed"], [.18, .22, .60])[0],
                  "power_kw": gen["power_kw"]})
write_jsonl("generator_dispatch.jsonl", gdisp)

welfare = []
prio_aff = [p for p in persons if p["gmina_code"] in affected_codes]
for i, p in enumerate(prio_aff[:720], 1):
    welfare.append({"event_time": iso(D0 + timedelta(hours=rng.uniform(6, 90))), "visit_id": f"VIS-{i:05d}",
                    "person_token": p["person_token"], "gmina_code": p["gmina_code"], "team_id": f"OSP-{random.randint(1, 90):03d}",
                    "result": random.choices(["contact_confirmed", "no_contact", "evacuation", "generator_needed"], [.62, .16, .13, .09])[0]})
write_jsonl("welfare_check.jsonl", welfare)

alerts = []
for g in gminas:
    send = D0 - timedelta(hours=6) if g["voivodeship_code"] in TARGET else D0 + timedelta(hours=2)
    for ch in ["RSO", "SMS", "local_radio"]:
        sent = int(int(g["population"]) * {"RSO": .55, "SMS": .82, "local_radio": .35}[ch])
        delivered = int(sent * clamp(rng.normal(.88 - (.30 if g["gmina_code"] in affected_codes else .04), .09), .25, .99))
        alerts.append({"event_time": iso(send + timedelta(minutes=random.randint(0, 180))), "gmina_code": g["gmina_code"], "channel": ch,
                       "messages_sent": sent, "messages_delivered": delivered, "messages_opened": int(delivered * clamp(rng.normal(.48, .11), .12, .82)),
                       "spo_code": "SPO-3"})
write_jsonl("alert_delivery.jsonl", alerts)

counts = {}
for p in DATA.glob("*.csv"):
    with p.open(encoding="utf-8") as f:
        counts[p.name] = max(0, sum(1 for _ in f) - 1)
for p in DATA.glob("*.jsonl"):
    with p.open(encoding="utf-8") as f:
        counts[p.name] = sum(1 for _ in f)
(DATA / "README.md").write_text(
    "# Datasets — Tarcza Zimowa\n\n"
    "> Dane są w 100% syntetyczne, wygenerowane proceduralnie (seed=42). Nie są danymi operacyjnymi żadnej instytucji. "
    "`fact_priority_persons.csv` zawiera wyłącznie fikcyjne, pseudonimowane rekordy demonstracyjne. Privacy-by-design: agregacja per gmina, minimalizacja, etykiety wrażliwości, RLS/Purview.\n\n"
    "## Liczby rekordów\n\n| Plik | Rekordy |\n|---|---:|\n"
    + "".join(f"| `{k}` | {v} |\n" for k, v in sorted(counts.items()))
    + "\n## Spójność\n\nAwaria kaskaduje w 4 województwach. BTS-y tracą zasięg po 4–8 h. Zgłoszenia 112 rosną z mrozem i czasem bez prądu. Autonomia placówek jest syntetyczna.\n",
    encoding="utf-8",
)
print(json.dumps(counts, ensure_ascii=False, indent=2))
