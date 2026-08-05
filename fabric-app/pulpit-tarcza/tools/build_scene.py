"""Buduje statyczna scene demo (public/data/scene.json) z datasets/ repozytorium ol-blackout-wrazliwi.

Dlaczego z plikow, a nie z Eventhouse:
- Eventhouse przechowuje wylacznie okno ostatniego odtwarzania (scenario/replay.py
  czysci tabele i pisze biezacym czasem), wiec nie zawiera pelnej sceny.
- datasets/ to deterministyczne zrodlo, z ktorego zasilany jest Lakehouse i Eventstream,
  wiec liczby w aplikacji zgadzaja sie z dashboardem i notatnikami.

Aplikacja pokazuje **przebieg w czasie**, nie jeden snapshot. `dynamic_risk_latest.csv`
zawiera wylacznie chwile 2026-01-16 18:00, dlatego IZZ jest tu przeliczany dla kazdej
godziny sceny **ta sama formula co notatnik 03_dynamic_risk.py**. Test regresyjny
sprawdza, ze klatka odpowiadajaca chwili notatnika daje te same liczby.

Uruchomienie:  python tools/build_scene.py
"""

from __future__ import annotations

import collections
import csv
import datetime
import json
import math
import unicodedata
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
DATA = ROOT / "datasets"
DERIVED = DATA / "derived"
OUT = APP / "public" / "data" / "scene.json"

UTC = datetime.timezone.utc

# Os czasu sceny. Kaskada startuje 14.01 o 06:02, kulminacja wypada 16.01,
# odbudowa konczy sie 19.01 - okno 14.01 00:00 .. 18.01 00:00 obejmuje caly
# przebieg z jedna doba tla przed pierwsza awaria.
T_START = datetime.datetime(2026, 1, 14, 0, 0, tzinfo=UTC)
T_END = datetime.datetime(2026, 1, 18, 0, 0, tzinfo=UTC)
STEP_H = 1

# Chwila, dla ktorej notatnik 03 policzyl dynamic_risk_latest.csv. Trzymana tu,
# zeby test regresyjny mial czego szukac.
NOTEBOOK_SNAPSHOT = datetime.datetime(2026, 1, 16, 16, 0, tzinfo=UTC)  # 18:00 +02:00

# Wagi IZZ - musza byc identyczne jak w notebooks/03_dynamic_risk.py.
W_IWL, W_OUTAGE, W_TEMP, W_TELECOM, W_RESCUE = 0.38, 0.30, 0.18, 0.09, 0.05
LEVELS = [(40, "monitoring"), (60, "elevated"), (75, "high"), (10**9, "critical")]

# Domyslne wartosci dla gmin bez odczytu - jak w notatniku.
DEFAULT_COVERAGE = 0.9
DEFAULT_FEELS_LIKE = -8.0


def read_csv(name: str) -> list[dict]:
    with open(DATA / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_derived(name: str) -> list[dict]:
    with open(DERIVED / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_json(name: str) -> dict:
    with open(DERIVED / name, encoding="utf-8") as f:
        return json.load(f)


def stream(name: str):
    with open(DATA / f"{name}.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def r1(x: float) -> float:
    return round(x, 1)


def r2(x: float) -> float:
    return round(x, 2)


def r3(x: float) -> float:
    """Wspolrzedne: trzy miejsca to ok. 100 m. Dwa miejsca (ok. 1 km) potrafily
    przesunac punkt lezacy przy granicy na jej druga strone."""
    return round(x, 3)


def parse_ts(text: str) -> datetime.datetime:
    """Generator zapisuje czas bez sekund (2026-01-14T12:12+02:00). To ta sama
    pulapka, ktora w notatniku 03 dawala po cichu null w Sparku."""
    return datetime.datetime.fromisoformat(text).astimezone(UTC)


def level_of(izz: float) -> str:
    for bound, name in LEVELS:
        if izz <= bound:
            return name
    return "critical"


# ---------------------------------------------------------------------------
# Korekta wspolrzednych
# ---------------------------------------------------------------------------
#
# `generate_datasets.py` rozrzuca gminy, punkty grzewcze, placowki opieki
# i agregaty losowym odchyleniem wokol srodka wojewodztwa, bez sprawdzania
# granic. Dopoki mapa rysowala sama siatke, nie bylo tego widac. Po naniesieniu
# prawdziwych granic czesc punktow ladowala na Baltyku albo za wschodnia granica.
#
# Poprawiamy to **wylacznie w warstwie prezentacji**, przy budowie sceny.
# Zbiory zrodlowe, derived/, notatniki, Eventhouse i model semantyczny zostaja
# nietkniete, wiec zaden wskaznik sie nie zmienia.

RINGS_FILE = Path(__file__).resolve().parent / "poland_rings.json"
INWARD = 0.06


def _fold(text: str) -> str:
    """Nazwy wojewodztw w zbiorach sa bez znakow diakrytycznych, w granicach - z."""
    text = text.replace("\u0142", "l").replace("\u0141", "L")
    stripped = unicodedata.normalize("NFD", text)
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").lower()


def load_regions() -> dict[str, list[list[list[float]]]]:
    if not RINGS_FILE.exists():
        raise SystemExit(
            f"brak {RINGS_FILE.name} - uruchom najpierw: python tools/build_poland_geo.py"
        )
    with open(RINGS_FILE, encoding="utf-8") as f:
        return {_fold(k): v for k, v in json.load(f).items()}


def in_region(lon: float, lat: float, rings: list[list[list[float]]]) -> bool:
    """Test parzystosci przeciec promienia poziomego."""
    inside = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            if (y1 > lat) != (y2 > lat):
                if lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                    inside = not inside
    return inside


def _km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return math.hypot((lon2 - lon1) * 68.5, (lat2 - lat1) * 111.2)


def snap_into(lon: float, lat: float, rings: list[list[list[float]]]) -> tuple[float, float]:
    """Najblizszy wierzcholek granicy, przesuniety w strone srodka wielokata.

    Przy wklesnych ksztaltach - a takie sa Lubuskie czy Pomorskie - pojedyncze
    zanurzenie potrafi nie wystarczyc, wiec zwiekszamy je, az punkt faktycznie
    znajdzie sie w srodku.
    """
    best_vertex = None
    best_centroid = (lon, lat)
    best_d = float("inf")
    for ring in rings:
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        for x, y in ring:
            d = _km(lon, lat, x, y)
            if d < best_d:
                best_d = d
                best_vertex = (x, y)
                best_centroid = (cx, cy)
    if best_vertex is None:
        return lon, lat

    vx, vy = best_vertex
    cx, cy = best_centroid
    for inward in (INWARD, 0.12, 0.25, 0.5):
        nx = round(vx + (cx - vx) * inward, 3)
        ny = round(vy + (cy - vy) * inward, 3)
        if in_region(nx, ny, rings):
            return nx, ny
    return round(cx, 3), round(cy, 3)


def correct_coordinates(
    gminas: dict[str, dict],
    voivs: dict[str, dict],
    *point_sets: tuple[list[dict], str],
) -> None:
    """Przesuwa punkty do wlasnych wojewodztw.

    `point_sets` to pary (lista wierszy, etykieta). Kazdy wiersz musi miec `lon`,
    `lat` i `gmina_code` albo `voivodeship_code` - punkty przypisane do gminy
    dziedzicza po niej wojewodztwo, bo w zbiorach nie maja wlasnego kodu.
    """
    regions = load_regions()
    voiv_name = {code: _fold(row["voivodeship_name"]) for code, row in voivs.items()}
    moved: dict[str, int] = collections.Counter()

    def fix(row: dict, voiv_code: str) -> bool:
        rings = regions.get(voiv_name.get(voiv_code, ""))
        if not rings or not row.get("lon") or not row.get("lat"):
            return False
        # Sprawdzamy wartosc juz zaokraglona, bo taka trafi na mape.
        lon, lat = r3(float(row["lon"])), r3(float(row["lat"]))
        if in_region(lon, lat, rings):
            row["lon"], row["lat"] = lon, lat
            return False
        row["lon"], row["lat"] = snap_into(lon, lat, rings)
        return True

    for row in gminas.values():
        if fix(row, row["voivodeship_code"]):
            moved["gminy"] += 1

    for rows, label in point_sets:
        for row in rows:
            code = row.get("voivodeship_code")
            if not code:
                g = gminas.get(row.get("gmina_code", ""))
                code = g["voivodeship_code"] if g else ""
            if fix(row, code):
                moved[label] += 1

    print("korekta wspolrzednych:", dict(moved) or "brak przesuniec")


# ---------------------------------------------------------------------------
# Budowa sceny
# ---------------------------------------------------------------------------


def build_frames(
    gminas: dict[str, dict],
    iwl: dict[str, dict],
    times: list[datetime.datetime],
) -> tuple[list[dict], dict[str, dict]]:
    """Przelicza IZZ dla kazdej godziny sceny.

    Zwraca liste klatek i mape statycznych skladnikow IZZ (te, ktore nie
    zaleza od czasu) potrzebna do sprawdzenia zgodnosci z notatnikiem.
    """
    # --- awarie: dla kazdej gminy ostatni stan <= t oraz pierwsze zdarzenie ---
    outages: dict[str, list[tuple[datetime.datetime, str, float]]] = collections.defaultdict(list)
    for row in stream("outage_events"):
        outages[row["gmina_code"]].append(
            (parse_ts(row["event_time"]), row["status"], float(row["customers_without_power"] or 0))
        )
    for rows in outages.values():
        rows.sort(key=lambda r: r[0])
    outage_start = {code: rows[0][0] for code, rows in outages.items()}

    # --- pokrycie telekomunikacyjne: ostatni odczyt <= t ---
    coverage: dict[str, list[tuple[datetime.datetime, float]]] = collections.defaultdict(list)
    for row in stream("telecom_coverage"):
        coverage[row["gmina_code"]].append((parse_ts(row["event_time"]), float(row["coverage_pct"])))
    for rows in coverage.values():
        rows.sort(key=lambda r: r[0])

    # --- pogoda: ostatni odczyt <= t, per powiat ---
    weather: dict[str, list[tuple[datetime.datetime, float]]] = collections.defaultdict(list)
    for row in stream("weather_readings"):
        weather[row["powiat_code"]].append((parse_ts(row["event_time"]), float(row["feels_like_c"])))
    for rows in weather.values():
        rows.sort(key=lambda r: r[0])

    # Skladniki niezalezne od czasu.
    static = {}
    for code, g in gminas.items():
        w = iwl.get(code)
        if not w:
            continue
        rescue = float(w["rescue_travel_time_min"])
        static[code] = {
            "iwl": float(w["iwl_score"]),
            "vuln": int(float(w["vulnerable_population_est"])),
            "rescue": rescue,
            "rescueComp": min(rescue / 75.0, 1.0),
            "pop": int(g["population"]),
        }

    # Kursory po posortowanych seriach - unikamy skanowania 522 tys. odczytow
    # telekomunikacyjnych raz na klatke.
    cur_out: dict[str, int] = collections.defaultdict(int)
    cur_cov: dict[str, int] = collections.defaultdict(int)
    cur_w: dict[str, int] = collections.defaultdict(int)
    last_out: dict[str, tuple[str, float]] = {}
    last_cov: dict[str, float] = {}
    last_w: dict[str, float] = {}

    frames = []
    for t in times:
        for code, rows in outages.items():
            i = cur_out[code]
            while i < len(rows) and rows[i][0] <= t:
                last_out[code] = (rows[i][1], rows[i][2])
                i += 1
            cur_out[code] = i
        for code, rows in coverage.items():
            i = cur_cov[code]
            while i < len(rows) and rows[i][0] <= t:
                last_cov[code] = rows[i][1]
                i += 1
            cur_cov[code] = i
        for pc, rows in weather.items():
            i = cur_w[pc]
            while i < len(rows) and rows[i][0] <= t:
                last_w[pc] = rows[i][1]
                i += 1
            cur_w[pc] = i

        rows_out = []
        for code, g in gminas.items():
            s = static.get(code)
            if not s:
                continue
            status, without = last_out.get(code, (None, 0.0))
            if status == "restored":
                without = 0.0
            hours = 0.0
            if status and status != "restored" and code in outage_start:
                hours = max((t - outage_start[code]).total_seconds() / 3600.0, 0.0)
            cov = last_cov.get(code, DEFAULT_COVERAGE)
            feels = last_w.get(g["powiat_code"], DEFAULT_FEELS_LIKE)

            temp_comp = min(max(-15.0 - feels, 0.0) / 15.0, 1.0)
            outage_comp = min(hours / 72.0, 1.0)
            telecom_comp = max(1.0 - cov, 0.0)
            izz = (
                W_IWL * (s["iwl"] / 100.0)
                + W_OUTAGE * outage_comp
                + W_TEMP * temp_comp
                + W_TELECOM * telecom_comp
                + W_RESCUE * s["rescueComp"]
            ) * 100.0
            vuln_no_power = round(s["vuln"] * min(max(without / s["pop"], 0.0), 1.0))

            # Do sceny trafiaja tylko gminy, ktore w danej chwili sa istotne:
            # z awaria albo z IZZ powyzej progu monitorowania. Pozostale 2200
            # gmin przy kazdej klatce to 90% objetosci pliku bez tresci decyzyjnej.
            if without <= 0 and izz < 40:
                continue
            rows_out.append(
                [
                    code,
                    r2(izz),
                    r1(hours),
                    int(without),
                    vuln_no_power,
                    r2(cov),
                    r1(feels),
                ]
            )

        rows_out.sort(key=lambda r: -r[1])
        frames.append({"t": t.isoformat().replace("+00:00", "Z"), "risk": rows_out})

    return frames, static


def bucket_events(times: list[datetime.datetime]):
    """Przypisuje zdarzenia strumieniowe do klatek. Zwraca funkcje indeksujaca."""
    step = datetime.timedelta(hours=STEP_H)

    def index_of(t: datetime.datetime) -> int | None:
        if t < times[0] or t > times[-1] + step:
            return None
        return min(int((t - times[0]) / step), len(times) - 1)

    return index_of


def main() -> None:
    times = []
    t = T_START
    while t <= T_END:
        times.append(t)
        t += datetime.timedelta(hours=STEP_H)

    voivs = {r["voivodeship_code"]: r for r in read_csv("dim_voivodeship.csv")}
    gminas = {r["gmina_code"]: r for r in read_csv("dim_gmina.csv")}
    powiats = {r["powiat_code"]: r for r in read_csv("dim_powiat.csv")}
    iwl = {r["gmina_code"]: r for r in read_derived("iwl_by_gmina.csv")}
    heating = read_csv("dim_heating_point.csv")
    generators = read_csv("dim_generator_stock.csv")
    facilities = read_csv("dim_care_facility.csv")
    persons = {r["person_token"]: r for r in read_csv("fact_priority_persons.csv")}
    queue = read_derived("welfare_check_queue.csv")
    routes = read_derived("welfare_check_routes.csv")
    selected = read_derived("selected_heating_points.csv")
    crossing = read_derived("critical_crossing_times.csv")
    whatif = read_derived("whatif_extended_outage.csv")

    correct_coordinates(
        gminas,
        voivs,
        (heating, "punkty grzewcze"),
        (generators, "agregaty"),
        (facilities, "placowki opieki"),
    )

    frames, static = build_frames(gminas, iwl, times)
    index_of = bucket_events(times)

    # --- zdarzenia operacyjne w klatkach ---
    hp_status: dict[int, list] = collections.defaultdict(list)
    for row in stream("heating_point_status"):
        i = index_of(parse_ts(row["event_time"]))
        if i is None:
            continue
        hp_status[i].append(
            [
                row["heating_point_id"],
                row["gmina_code"],
                row["status"],
                int(row["occupancy"]),
                int(row["capacity"]),
                1 if row["needs_food"] else 0,
                1 if row["needs_medical_support"] else 0,
                1 if row["needs_generator"] else 0,
            ]
        )

    dispatch: dict[int, list] = collections.defaultdict(list)
    for row in stream("generator_dispatch"):
        i = index_of(parse_ts(row["event_time"]))
        if i is None:
            continue
        dispatch[i].append(
            [
                row["dispatch_id"],
                row["generator_id"],
                row["target_type"],
                row["gmina_code"],
                row["status"],
                int(row["power_kw"]),
            ]
        )

    visits: dict[int, list] = collections.defaultdict(list)
    for row in stream("welfare_check"):
        i = index_of(parse_ts(row["event_time"]))
        if i is None:
            continue
        visits[i].append(
            [row["visit_id"], row["person_token"], row["gmina_code"], row["team_id"], row["result"]]
        )

    calls: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    calls_by_gmina: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in stream("emergency_calls"):
        i = index_of(parse_ts(row["event_time"]))
        if i is None:
            continue
        calls[i][row["call_type"]] += 1
        calls[i]["_" + row["priority"]] += 1
        calls_by_gmina[i][row["gmina_code"]] += 1

    alerts: dict[int, dict] = collections.defaultdict(
        lambda: {"sent": 0, "delivered": 0, "opened": 0, "ch": collections.Counter()}
    )
    alerts_by_gmina: dict[str, dict] = collections.defaultdict(lambda: {"sent": 0, "delivered": 0})
    for row in stream("alert_delivery"):
        i = index_of(parse_ts(row["event_time"]))
        g = alerts_by_gmina[row["gmina_code"]]
        g["sent"] += int(row["messages_sent"])
        g["delivered"] += int(row["messages_delivered"])
        if i is None:
            continue
        a = alerts[i]
        a["sent"] += int(row["messages_sent"])
        a["delivered"] += int(row["messages_delivered"])
        a["opened"] += int(row["messages_opened"])
        a["ch"][row["channel"]] += int(row["messages_delivered"])

    for i, frame in enumerate(frames):
        frame["hp"] = hp_status.get(i, [])
        frame["disp"] = dispatch.get(i, [])
        frame["visits"] = visits.get(i, [])
        c = calls.get(i)
        frame["calls"] = (
            {k: v for k, v in sorted(c.items(), key=lambda kv: -kv[1])} if c else {}
        )
        frame["callsG"] = dict(calls_by_gmina.get(i, {}))
        a = alerts.get(i)
        frame["alerts"] = (
            {"sent": a["sent"], "delivered": a["delivered"], "opened": a["opened"], "ch": dict(a["ch"])}
            if a
            else {}
        )

    # --- statyczne slowniki ---
    scene_gminas = []
    for code, g in gminas.items():
        s = static.get(code)
        if not s:
            continue
        scene_gminas.append(
            {
                "c": code,
                "n": g["gmina_name"],
                "v": g["voivodeship_code"],
                "p": g["powiat_code"],
                "lat": g["lat"],
                "lon": g["lon"],
                "pop": s["pop"],
                "iwl": r2(s["iwl"]),
                "vuln": s["vuln"],
                "rescue": r1(s["rescue"]),
                "type": g["gmina_type"],
            }
        )

    sel_scores = {r["heating_point_id"]: r for r in selected}
    scene_heating = [
        {
            "id": h["heating_point_id"],
            "g": h["gmina_code"],
            "type": h["heating_point_type"],
            "cap": int(h["capacity"]),
            "lat": h["lat"],
            "lon": h["lon"],
            "gen": h["has_generator"] == "True",
            "stove": h["has_independent_stove"] == "True",
            "kw": r1(float(h["power_need_kw"])),
            "avail": h["availability_status"],
            "sel": h["heating_point_id"] in sel_scores,
            "score": r2(float(sel_scores[h["heating_point_id"]]["score"]))
            if h["heating_point_id"] in sel_scores
            else None,
            "covered": int(float(sel_scores[h["heating_point_id"]]["covered_vulnerable_est"]))
            if h["heating_point_id"] in sel_scores
            else 0,
        }
        for h in heating
    ]

    scene_generators = [
        {
            "id": r["generator_id"],
            "wh": r["warehouse_id"],
            "v": r["voivodeship_code"],
            "kw": int(float(r["power_kw"])),
            "fuel": r["fuel_type"],
            "mob": r["mobility_type"],
            "status": r["status"],
            "lat": r["lat"],
            "lon": r["lon"],
        }
        for r in generators
    ]

    scene_facilities = [
        {
            "id": r["facility_id"],
            "g": r["gmina_code"],
            "type": r["facility_type"],
            "cap": int(r["capacity"]),
            "occ": int(r["current_occupancy"]),
            "gen": r["has_generator"] == "True",
            "auto": r1(float(r["generator_autonomy_hours"] or 0)),
            "kw": r1(float(r["power_need_kw"])),
            "lat": r["lat"],
            "lon": r["lon"],
        }
        for r in facilities
    ]

    scene_queue = []
    for r in queue:
        p = persons.get(r["person_token"], {})
        scene_queue.append(
            {
                "rank": int(r["queue_rank"]),
                "token": r["person_token"],
                "cat": r["category"],
                "g": r["gmina_code"],
                "prio": r2(float(r["priority_score"])),
                "auto": r1(float(r["medical_device_autonomy_hours"] or 0)),
                "age": r["age_band"],
                "alone": r["is_living_alone"] == "True",
                "cov": r2(float(r["coverage_pct"] or 0)),
                "hours": r1(float(r["hours_without_power"] or 0)),
                "contact": p.get("fictional_contact", ""),
            }
        )

    by_team: dict[str, list] = collections.defaultdict(list)
    for r in routes:
        by_team[r["team_id"]].append(
            {
                "seq": int(r["sequence"]),
                "token": r["person_token"],
                "g": r["gmina_code"],
                "eta": r1(float(r["eta_min"])),
                "action": r["action"],
            }
        )
    scene_routes = [
        {"team": team, "stops": sorted(stops, key=lambda s: s["seq"])}
        for team, stops in sorted(by_team.items())
    ]

    scene_crossing = [
        {
            "g": r["gmina_code"],
            "n": r["gmina_name"],
            "t": r["first_critical_time"],
            "izz": r2(float(r["izz_score_at_snapshot"])),
            "drivers": r["main_drivers"],
        }
        for r in crossing
    ]

    whatif_rows = sorted(
        (
            {
                "g": r["gmina_code"],
                "n": r["gmina_name"],
                "izz": r2(float(r["izz_score"])),
                "whatif": r2(float(r["whatif_izz"])),
                "delta": r2(float(r["whatif_izz"]) - float(r["izz_score"])),
            }
            for r in whatif
        ),
        key=lambda r: -r["delta"],
    )

    scene = {
        "meta": {
            "generated": datetime.datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "tStart": times[0].isoformat().replace("+00:00", "Z"),
            "tEnd": times[-1].isoformat().replace("+00:00", "Z"),
            "stepHours": STEP_H,
            "frames": len(frames),
            "notebookSnapshot": NOTEBOOK_SNAPSHOT.isoformat().replace("+00:00", "Z"),
            "weights": {
                "iwl": W_IWL,
                "outage": W_OUTAGE,
                "temp": W_TEMP,
                "telecom": W_TELECOM,
                "rescue": W_RESCUE,
            },
        },
        "voivodeships": [
            {"c": c, "n": r["voivodeship_name"], "lat": r["lat"], "lon": r["lon"], "axis": r["scenario_axis"]}
            for c, r in sorted(voivs.items())
        ],
        "powiats": [
            {"c": c, "v": r["voivodeship_code"], "n": r["powiat_name"]}
            for c, r in sorted(powiats.items())
        ],
        "gminas": scene_gminas,
        "heatingPoints": scene_heating,
        "generators": scene_generators,
        "facilities": scene_facilities,
        "queue": scene_queue,
        "routes": scene_routes,
        "crossing": scene_crossing,
        "whatif": whatif_rows[:60],
        "alertsByGmina": {
            k: [v["sent"], v["delivered"]] for k, v in alerts_by_gmina.items() if v["sent"] > 0
        },
        "frames": frames,
        "summaries": {
            "iwl": read_json("iwl_summary.json"),
            "risk": read_json("dynamic_risk_summary.json"),
            "heating": read_json("heating_point_optimization_summary.json"),
            "welfare": read_json("welfare_check_summary.json"),
            "whatif": read_json("whatif_summary.json"),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(scene, f, ensure_ascii=False, separators=(",", ":"))

    size = OUT.stat().st_size
    peak = max(frames, key=lambda fr: sum(1 for r in fr["risk"] if r[1] >= 75))
    print(f"zapisano:        {OUT}  ({size / 1024:.0f} kB)")
    print(f"klatek:          {len(frames)}  ({times[0]:%Y-%m-%d %H:%M} .. {times[-1]:%Y-%m-%d %H:%M} UTC)")
    print(f"gmin:            {len(scene_gminas)}")
    print(f"punktow grzew.:  {len(scene_heating)}  (wskazanych {len(selected)})")
    print(f"agregatow:       {len(scene_generators)}")
    print(f"placowek opieki: {len(scene_facilities)}")
    print(f"kolejka wizyt:   {len(scene_queue)}  w {len(scene_routes)} zespolach")
    print(f"szczyt krytycz.: {peak['t']} - {sum(1 for r in peak['risk'] if r[1] >= 75)} gmin IZZ>=75")
    snap = min(frames, key=lambda fr: abs(datetime.datetime.fromisoformat(fr["t"].replace("Z", "+00:00")) - NOTEBOOK_SNAPSHOT))
    print(f"klatka notatnika:{snap['t']} - max IZZ {max((r[1] for r in snap['risk']), default=0)}")


if __name__ == "__main__":
    main()
