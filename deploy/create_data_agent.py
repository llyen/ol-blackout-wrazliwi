"""Data Agent "Zapytaj o dane" scenariusza blackoutu wg `ai/DATA_AGENT.md`.

Definicja elementu `DataAgent`:

    Files/Config/data_agent.json                        wersja schematu
    Files/Config/draft/stage_config.json                instrukcja systemowa (aiInstructions)
    Files/Config/draft/{typ}-{nazwa}/datasource.json    zrodlo danych + wybrane elementy

Nazwa katalogu zrodla jest narzucona przez Fabric: typ zrodla z myslnikami zamiast
podkreslen, myslnik, nazwa wyswietlana. Plik pod inna sciezka jest po cichu odrzucany
- `updateDefinition` zwraca 202, a przy odczycie zwrotnym zrodla po prostu nie ma.

Uzycie:
    python deploy/create_data_agent.py
    python deploy/create_data_agent.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
SPEC = ROOT / "ai" / "DATA_AGENT.md"
API = "https://api.fabric.microsoft.com/v1"

AGENT_NAME = "agent_blackout_wrazliwi"
AGENT_DESC = ("Data Agent: pytania o ryzyko IZZ, osoby wrazliwe, punkty grzewcze, "
              "wizyty kontrolne i awarie zasilania w scenariuszu blackoutu zimowego")
KQL_DB = "OL_BLK_Eventhouse"

SCHEMA_AGENT = ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/"
                "definition/dataAgent/2.1.0/schema.json")
SCHEMA_STAGE = ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/"
                "definition/stageConfiguration/1.0.0/schema.json")
SCHEMA_SOURCE = ("https://developer.microsoft.com/json-schemas/fabric/item/dataAgent/"
                 "definition/dataSource/1.0.0/schema.json")

# Tabele merytoryczne z `deploy/lakehouse_schemas.json`. Pomijamy `dim_vulnerability_factors`
# - to czysto techniczny slownik wag skladnikow IWL (factor_code, weight, normalization),
# oznaczony jako ukryty w modelu semantycznym (`model_spec.HIDDEN_TABLES`), a nie dane
# operacyjne dla decydenta.
LAKEHOUSE_TABLES = [
    "dynamic_risk_latest", "critical_gminas_latest", "critical_crossing_times",
    "iwl_by_gmina", "fact_population_vulnerability", "fact_priority_persons",
    "selected_heating_points", "heating_point_status", "welfare_check_queue",
    "welfare_check_routes", "welfare_check", "whatif_extended_outage",
    "alert_delivery", "emergency_calls", "telecom_coverage", "outage_events",
    "weather_readings", "generator_dispatch",
    "dim_gmina", "dim_powiat", "dim_voivodeship",
    "dim_care_facility", "dim_heating_point", "dim_generator_stock",
]

# Tabele KQL w OL_BLK_Eventhouse (zweryfikowane). Nazwy inne niz w Lakehouse - Eventhouse
# trzyma surowe strumienie i rejestry, Lakehouse wyniki notatnikow.
KUSTO_TABLES = [
    "WeatherReadings", "OutageEvents", "TelecomCoverage", "EmergencyCalls",
    "HeatingPointStatus", "GeneratorDispatch", "WelfareCheck", "AlertDelivery",
    "dim_voivodeship", "dim_powiat", "dim_gmina", "CareFacilities", "HeatingPoints",
    "GeneratorStock", "GridAssets", "PopulationVulnerability", "PriorityPersons",
]

# Funkcje KQL weryfikujemy, ale NIE dodajemy jako `elements` - backend Data Agenta
# odrzuca elementy typu `kusto.functions` (`updateDefinition` konczy sie UnknownError).
# Ich sygnatury i przeznaczenie opisujemy w podpowiedzi zrodla.
KUSTO_FUNCTIONS = [
    "CurrentOutageByGmina", "OutageHoursByGmina", "CurrentTelecomCoverage",
    "CurrentHeatingPointStatus", "EmergencyCalls15m", "CareFacilityAutonomyState",
]

LAKEHOUSE_HINT = (
    "Trwaly obraz scenariusza i wyniki notatnikow analitycznych. "
    "`dynamic_risk_latest` to najswiezszy stan ryzyka IZZ per gmina ze skladnikami "
    "(temp_component, outage_component, telecom_component, rescue_component) i "
    "`vulnerable_without_power`; `critical_gminas_latest` to gminy w stanie krytycznym "
    "(scenariusz: 14), `critical_crossing_times` to moment przekroczenia progu. "
    "`iwl_by_gmina` niesie Indeks Wrazliwosci na Zimno (IWL) z rozbiciem na czynniki, "
    "`fact_population_vulnerability` to populacja wrazliwa per gmina. "
    "`selected_heating_points` to wskazane punkty grzewcze (scenariusz: 80, czesc z "
    "agregatami), `heating_point_status` to biezace zajecie punktow. "
    "`welfare_check_queue` to kolejka wizyt kontrolnych (500 osob), "
    "`welfare_check_routes` to zaplanowane trasy zespolow, `welfare_check` to zdarzenia "
    "wizyt. `whatif_extended_outage` to wariant przedluzonej awarii. "
    "`fact_priority_persons` zawiera kolumne `fictional_contact` (fikcyjne dane kontaktowe) "
    "i `sensitivity_label` - NIGDY nie ujawniaj kontaktow ani list imiennych, podawaj "
    "wylacznie agregaty. Wszystkie tabele maja `is_synthetic` = true - dane sa syntetyczne "
    "i demonstracyjne."
)
KUSTO_HINT = (
    "Surowe strumienie zdarzen i rejestry naplywajace w czasie: awarie, pogoda, lacznosc, "
    "zgloszenia 112, punkty grzewcze, dysponowanie agregatow, wizyty kontrolne, alerty. "
    "Dane sa datowane na scenariusz demonstracyjny (2026-01-12 .. 2026-01-16, D0 = 14.01), "
    "wiec `now()` i `ago()` moga nie zwrocic niczego - siegaj po gotowe funkcje bazy "
    "zamiast pisac logike okna czasu od zera:\n"
    "- `CurrentOutageByGmina()` - biezacy stan awarii zasilania per gmina.\n"
    "- `OutageHoursByGmina()` - liczba godzin bez pradu per gmina.\n"
    "- `CurrentTelecomCoverage()` - biezace pokrycie telekomunikacyjne per gmina.\n"
    "- `CurrentHeatingPointStatus()` - biezacy stan i zajecie punktow grzewczych.\n"
    "- `EmergencyCalls15m()` - zgloszenia alarmowe z ostatnich 15 minut sceny.\n"
    "- `CareFacilityAutonomyState()` - stan autonomii zasilania placowek opiekunczych.\n"
    "Tabele strumieniowe (`OutageEvents`, `TelecomCoverage`, `HeatingPointStatus`) powtarzaja "
    "stan przy kazdej zmianie, wiec licz po ostatnim zdarzeniu na klucz (gmina/obiekt), a nie "
    "po liczbie wierszy. `PriorityPersons` zawiera dane osobowe - podawaj tylko agregaty."
)
MODEL_HINT = (
    "Model semantyczny Direct Lake (OL_BLK_SemanticModel) z miarami nazwanymi po polsku "
    "(np. `Osoby wrazliwe bez zasilania`, `Gminy krytyczne`, `Pokrycie punktami grzewczymi %`, "
    "`Przyrost gmin krytycznych`). Uzywaj go do pytan o agregaty, udzialy i wskazniki zamiast "
    "liczyc je recznie z tabel - miary maja juz wbudowana poprawna logike (ostatni stan awarii, "
    "odsiew duplikatow strumieni, progi krytycznosci)."
)


def naglowek_autoryzacji(tok: str) -> str:
    """Skladane z czesci celowo - literal '******' bywa redagowany przy zapisie."""
    return " ".join(("Bearer", tok))


def token(resource: str) -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def instructions() -> str:
    """Instrukcja systemowa zlozona z `ai/DATA_AGENT.md`, zeby specyfikacja i wdrozenie
    nie rozjechaly sie w czasie. Specyfikacja blackoutu nie ma jednej sekcji "do wklejenia",
    wiec skladamy instrukcje z akapitu wprowadzajacego oraz sekcji, ktore realnie ksztaltuja
    zachowanie agenta: reguly odpowiedzi, zasady odmowy, styl i przykladowe pytania."""
    text = SPEC.read_text(encoding="utf-8")

    def sekcja(tytul: str) -> str:
        m = re.search(rf"##\s+{re.escape(tytul)}\s*\n(.*?)(?=\n##\s|\Z)", text, re.S)
        return m.group(1).strip() if m else ""

    m = re.search(r"\A(.*?)(?=\n##\s)", text, re.S)
    intro = m.group(1).strip() if m else ""
    intro = re.sub(r"\A#[^\n]*\n", "", intro).strip()  # usun naglowek H1

    reguly = sekcja("Reguły odpowiedzi")
    odmowy = sekcja("Zasady odmowy")
    styl = sekcja("Styl odpowiedzi")
    pytania = sekcja("Przykładowe pytania i oczekiwane odpowiedzi")

    if len(intro) < 150 or not reguly or not odmowy:
        sys.exit("Niepelna specyfikacja ai/DATA_AGENT.md - brak akapitu wprowadzajacego "
                 "lub sekcji 'Reguly odpowiedzi'/'Zasady odmowy'.")

    czesci = [intro]
    if reguly:
        czesci.append("Reguly odpowiedzi:\n" + reguly)
    if odmowy:
        czesci.append("Zasady odmowy:\n" + odmowy)
    if styl:
        czesci.append("Styl odpowiedzi:\n" + styl)
    if pytania:
        czesci.append("Typowe pytania uzytkownikow i oczekiwany sposob odpowiedzi:\n" + pytania)
    return "\n\n".join(czesci)


def lakehouse_tables(ws: str, lhid: str, hdr: dict) -> set[str]:
    r = requests.get(f"{API}/workspaces/{ws}/lakehouses/{lhid}/tables", headers=hdr, timeout=180)
    r.raise_for_status()
    return {t["name"] for t in r.json().get("data", [])}


def kusto_names(cluster: str, tk: str, what: str) -> set[str]:
    r = requests.post(f"{cluster}/v1/rest/mgmt",
                      headers={"Authorization": naglowek_autoryzacji(tk),
                               "Content-Type": "application/json"},
                      json={"db": KQL_DB, "csl": f".show {what}"}, timeout=180)
    r.raise_for_status()
    return {row[0] for row in r.json()["Tables"][0]["Rows"]}


def model_tables() -> set[str]:
    """Nazwy tabel modelu odpowiadaja kluczom `deploy/lakehouse_schemas.json`. Importu
    `create_semantic_model.py` unikamy - parsuje argumenty wiersza polecen przy wczytaniu.
    Tabele ukryte w modelu (`model_spec.HIDDEN_TABLES`, slowniki techniczne) pomijamy,
    tak samo jak w liscie Lakehouse - agentowi nie sa potrzebne."""
    schemas = json.loads((ROOT / "deploy" / "lakehouse_schemas.json").read_text(encoding="utf-8"))
    hidden: set[str] = set()
    try:
        sys.path.insert(0, str(ROOT / "deploy"))
        import model_spec  # noqa: PLC0415
        hidden = set(getattr(model_spec, "HIDDEN_TABLES", set()))
    except Exception:
        hidden = set()
    return set(schemas) - hidden


def element(name: str, kind: str) -> dict:
    return {"display_name": name, "type": kind, "is_selected": True, "children": []}


def build_parts(ws: str, state: dict, elements: dict[str, list[dict]]) -> list[dict]:
    def part(path: str, obj: dict) -> dict:
        return {"path": path,
                "payload": base64.b64encode(
                    json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")).decode(),
                "payloadType": "InlineBase64"}

    sources = [
        ("lh_blackout", "lakehouse_tables", state["lakehouseId"], LAKEHOUSE_HINT,
         "Wyniki analiz IWL/IZZ, kolejki wizyt, punkty grzewcze i rejestry scenariusza"),
        (KQL_DB, "kusto", state["kqlDatabaseId"], KUSTO_HINT,
         "Surowe strumienie zdarzen i rejestry: awarie, pogoda, lacznosc, 112, wizyty"),
        ("sm_blackout", "semantic_model", state["semanticModelId"], MODEL_HINT,
         "Model semantyczny z miarami ryzyka, pokrycia i osob wrazliwych"),
    ]

    parts = [
        part("Files/Config/data_agent.json", {"$schema": SCHEMA_AGENT}),
        part("Files/Config/draft/stage_config.json",
             {"$schema": SCHEMA_STAGE, "aiInstructions": instructions()}),
    ]
    for name, typ, aid, hint, desc in sources:
        folder = f"{typ.replace('_', '-')}-{name}"
        parts.append(part(f"Files/Config/draft/{folder}/datasource.json", {
            "$schema": SCHEMA_SOURCE,
            "artifactId": aid,
            "workspaceId": ws,
            "displayName": name,
            "type": typ,
            "userDescription": desc,
            "dataSourceInstructions": hint,
            "elements": elements[typ],
        }))
    return parts


def wait(r, hdr, want_result=False):
    if r.status_code != 202:
        return r
    loc = r.headers.get("Location")
    for _ in range(90):
        time.sleep(5)
        o = requests.get(loc, headers=hdr, timeout=120).json()
        if o.get("status") in ("Succeeded", "Completed", "Failed"):
            if o.get("status") == "Failed":
                sys.exit(f"Operacja nieudana: {json.dumps(o)[:800]}")
            break
    return requests.get(loc + "/result", headers=hdr, timeout=180) if want_result else r


def find_existing(ws: str, hdr: dict) -> str | None:
    r = requests.get(f"{API}/workspaces/{ws}/items?type=DataAgent", headers=hdr, timeout=120)
    r.raise_for_status()
    for it in r.json().get("value", []):
        if it["displayName"] == AGENT_NAME:
            return it["id"]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, cluster = state["workspaceId"], state["kustoQueryUri"]
    hdr = {"Authorization": naglowek_autoryzacji(token("https://api.fabric.microsoft.com")),
           "Content-Type": "application/json"}
    ktk = token("https://kusto.kusto.windows.net")

    print("Sprawdzam, czy wskazane elementy istnieja w zrodlach...")
    have_lh = lakehouse_tables(ws, state["lakehouseId"], hdr)
    have_kt = kusto_names(cluster, ktk, "tables")
    have_kf = kusto_names(cluster, ktk, "functions")
    have_sm = model_tables()

    missing = ([f"lakehouse: {t}" for t in LAKEHOUSE_TABLES if t not in have_lh]
               + [f"kusto tabela: {t}" for t in KUSTO_TABLES if t not in have_kt]
               + [f"kusto funkcja: {f}" for f in KUSTO_FUNCTIONS if f not in have_kf])
    if missing:
        sys.exit("Brakuje elementow w zrodlach:\n  " + "\n  ".join(missing))

    elements = {
        "lakehouse_tables": [element(t, "lakehouse_tables.table") for t in LAKEHOUSE_TABLES],
        "kusto": [element(t, "kusto.table") for t in KUSTO_TABLES],
        "semantic_model": [element(t, "semantic_model.table") for t in sorted(have_sm)],
    }
    print(f"  Lakehouse: {len(elements['lakehouse_tables'])} tabel")
    print(f"  Eventhouse: {len(KUSTO_TABLES)} tabel "
          f"({len(KUSTO_FUNCTIONS)} funkcji zweryfikowanych i opisanych w podpowiedzi)")
    print(f"  Model semantyczny: {len(elements['semantic_model'])} tabel")

    instr = instructions()
    print(f"  Instrukcja systemowa: {len(instr)} znakow")

    parts = build_parts(ws, state, elements)
    if args.dry_run:
        for p in parts:
            print(f"--- {p['path']}")
            print(base64.b64decode(p["payload"]).decode("utf-8")[:900])
        return

    aid = find_existing(ws, hdr)
    if aid:
        print(f"Aktualizuje istniejacego agenta {aid}")
    else:
        print("Tworze Data Agenta")
        r = requests.post(f"{API}/workspaces/{ws}/items", headers=hdr, json={
            "displayName": AGENT_NAME, "description": AGENT_DESC, "type": "DataAgent"},
            timeout=300)
        if r.status_code not in (200, 201, 202):
            sys.exit(f"create {r.status_code}: {r.text[:1200]}")
        aid = r.json()["id"]

    r = requests.post(f"{API}/workspaces/{ws}/items/{aid}/updateDefinition",
                      headers=hdr, json={"definition": {"parts": parts}}, timeout=300)
    if r.status_code not in (200, 202):
        sys.exit(f"updateDefinition {r.status_code}: {r.text[:1200]}")
    wait(r, hdr)

    # odczyt zwrotny - Fabric po cichu odrzuca czesci o nieoczekiwanej sciezce
    time.sleep(5)
    d = requests.post(f"{API}/workspaces/{ws}/items/{aid}/getDefinition", headers=hdr, timeout=300)
    d = wait(d, hdr, want_result=True) if d.status_code == 202 else d
    got = {p["path"]: json.loads(base64.b64decode(p["payload"]).decode("utf-8"))
           for p in d.json()["definition"]["parts"] if p["path"].endswith(".json")}
    srcs = {p: o for p, o in got.items() if p.endswith("datasource.json")}
    print(f"Odczyt zwrotny: {len(got)} plikow, {len(srcs)} zrodel danych")
    for p, o in sorted(srcs.items()):
        print(f"  {o['displayName']:24} {o['type']:16} {len(o.get('elements', []))} elementow")
    if len(srcs) != 3:
        sys.exit("Nie wszystkie zrodla zostaly przyjete przez Fabric.")
    if any(not o.get("elements") for o in srcs.values()):
        sys.exit("Ktores zrodlo ma pusta liste elementow.")
    stage = got.get("Files/Config/draft/stage_config.json", {})
    if not (stage.get("aiInstructions") or "").strip():
        sys.exit("Instrukcja systemowa nie zostala zapisana.")

    state["dataAgentId"] = aid
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGotowe. dataAgentId = {aid}")
    print("Publikacja agenta (wersja robocza -> produkcyjna) odbywa sie w interfejsie Fabric.")


if __name__ == "__main__":
    main()
