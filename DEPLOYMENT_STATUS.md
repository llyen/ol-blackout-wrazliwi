# 🚀 Stan wdrożenia scenariusza „Tarcza Zimowa" na Microsoft Fabric

Dokument opisuje **rzeczywisty, zweryfikowany** stan środowiska demonstracyjnego oraz kolejność
kroków, którymi zostało ono zbudowane. Służy do odtworzenia wdrożenia i do rozliczenia prac.

Scenariusz: kaskadowa awaria sieci elektroenergetycznej w czasie mrozu, ochrona ludności
wrażliwej (Polska północno-wschodnia i wschodnia — podlaskie, warmińsko-mazurskie, lubelskie,
mazowieckie).

## 1. Środowisko

| Element | Wartość |
|---|---|
| Workspace | `OL-ZK-Demo-Blackout` |
| Workspace ID | `68e1369e-bc4d-4c87-a747-e3fd78c21f21` |
| Pojemność | `fcdemo` (F8) |
| Cluster URI Eventhouse | `https://trd-bv9kuej96btp7bpuq7.z6.kusto.fabric.microsoft.com` |

> Pojemność `fcdemo` sama przechodzi w stan `Paused` po okresie bezczynności. Przed każdym
> dłuższym wdrożeniem uruchom `deploy\ensure_capacity.ps1`, inaczej wywołania Fabric API
> kończą się błędem `CapacityNotActive`.

## 2. Utworzone elementy

| Element | Typ | ID |
|---|---|---|
| `OL_BLK_Lakehouse` | Lakehouse | `49e3e20d-6da3-44b0-8273-ad6cd8290359` |
| `OL_BLK_Eventhouse` | KQL Database | `2b228a24-f180-4b27-a916-688208854533` |
| `OL_BLK_Dashboard` | Real-Time Dashboard | `c66f0b86-e880-415a-819d-25ed71c5d123` |
| `OL_BLK_Activator` | Activator (Reflex) | `03cc6e17-8be9-4114-ab0a-e404692c43f0` |
| `01_load_dimensions` … `06_whatif` | Notebook (8) | zob. workspace |

## 3. Kolejność wdrożenia

```powershell
# 0. Upewnienie się, że pojemność działa
.\deploy\ensure_capacity.ps1

# 1. Workspace, Lakehouse, Eventhouse
.\deploy\deploy_fabric.ps1 -Step items

# 2. Wysyłka danych do OneLake (CSV -> Files/datasets, JSONL -> Files/streams), ok. 110 MB
.\deploy\deploy_fabric.ps1 -Step upload

# 3. Tabele KQL, polityki retencji, funkcje curated
.\deploy\deploy_fabric.ps1 -Step kql

# 4. Ingestia 8 strumieni i 9 wymiarów/rejestrów
.\deploy\deploy_fabric.ps1 -Step ingest
.\deploy\deploy_fabric.ps1 -Step kql      # ponownie: funkcje odwołują się do rejestrów
.\deploy\deploy_fabric.ps1 -Step verify

# 5. Notatniki Spark: wymiary, strumienie, IWL, IZŻ, lokalizacja punktów, priorytety wizyt
.\deploy\import_notebooks.ps1
.\deploy\run_notebooks.ps1

# 6. Real-Time Dashboard (5 stron, 22 kafelki)
.\deploy\create_dashboard.ps1

# 7. Reguły alertowe jako funkcje KQL + element Activator (8 reguł)
.\deploy\create_activator.ps1

# 8. Symulacja czasu rzeczywistego (tryb ciągły, w tle)
.\scenario\run_scenario.ps1 -Preset ciagly -Background
```

> **Kolejność `upload` → `kql` → `ingest` → `kql` nie jest przypadkowa.** Funkcja
> `CareFacilityAutonomyState` odwołuje się do rejestru `CareFacilities`, który powstaje dopiero
> w kroku `ingest`. Przy pierwszym przebiegu kroku `kql` ta funkcja kończy się błędem 400.

## 4. Zweryfikowane liczności w Eventhouse

Stan po pełnym załadowaniu danych źródłowych (`-Step verify`):

| Tabela | Wiersze |
|---|---|
| `TelecomCoverage` | 522 647 |
| `WeatherReadings` | 201 020 |
| `AlertDelivery` | 7 431 |
| `OutageEvents` | 6 650 |
| `EmergencyCalls` | 5 285 |
| `dim_gmina` | 2 477 |
| `PopulationVulnerability` | 2 477 |
| `HeatingPointStatus` | 1 780 |
| `PriorityPersons` | 1 200 |
| `HeatingPoints` | 620 |
| `CareFacilities` | 520 |
| `GeneratorDispatch` | 480 |
| `GridAssets` | 420 |
| `dim_powiat` | 380 |
| `GeneratorStock` | 300 |
| `WelfareCheck` | 260 |
| `dim_voivodeship` | 16 |

Zakres czasu danych źródłowych: `2026-01-12` … `2026-01-16` (D0 = 14.01.2026).

> W trybie ciągłego odtwarzania tabele strumieniowe zawierają wyłącznie okno prezentacji
> (tło + faza live przesunięte na bieżący zegar), więc ich liczności są mniejsze.
> Pełne liczności wracają po `deploy_fabric.ps1 -Step ingest`.

## 5. Tabele Delta w Lakehouse (25)

Wymiary i rejestry (notatnik `01`): `dim_voivodeship`, `dim_powiat`, `dim_gmina`,
`dim_grid_asset`, `dim_care_facility`, `dim_heating_point`, `dim_generator`,
`dim_priority_person`, `dim_population_vulnerability`.

Strumienie (notatnik `01b`): `fact_outage`, `fact_weather`, `fact_telecom`,
`fact_emergency_call`, `fact_heating_point_status`, `fact_generator_dispatch`,
`fact_welfare_check`, `fact_alert_delivery`.

Wyniki modeli (notatniki `02`–`06`): `vulnerability_index` (IWL), `dynamic_risk` (IZŻ),
`critical_gminas` (14 gmin), `heating_point_siting` (80 wskazanych punktów),
`welfare_check_priority` (500 osób w kolejce), `welfare_route_stops` (147 przystanków),
`whatif_scenarios`.

## 6. Ścieżka real-time

```
scenario/replay.py  ──►  streaming ingestion Eventhouse  ──►  Real-Time Dashboard (okno 15 min)
```

Silnik odtwarzania kompresuje dobę scenariusza do 24 minut zegara (`--speed 60`) i **przypina
oś czasu do chwili uruchomienia**, dlatego dashboard pokazuje świeże dane niezależnie od pory
demonstracji. Tło (12–14.01 do godz. 12:00) ładowane jest wsadowo z OneLake i przesuwane jednym
poleceniem `.set-or-replace`, a okno live idzie strumieniowo.

**Punkt startu okna live: `2026-01-14 12:00`.** To jedyna chwila, w której tło jest już niepuste
(ostrzeżenia SPO-3 i pierwszy etap kaskady mają za sobą), a okno live zawiera wszystkie pięć
rodzajów działań operacyjnych: awarie, punkty grzewcze, wizyty opiekuńcze, dysponowanie
agregatów i zgłoszenia 112.

| Wariant | Tempo | Okno live | Czas cyklu |
|---|---|---|---|
| `demo` | 60x | 24 h | ~24 min |
| `szybki` | 300x | 24 h | ~5 min (smoke-test) |
| `kaskada` | 30x | 12 h od kulminacji | ~24 min |
| `wolny` | 15x | 12 h | ~48 min |
| `ciagly` | 60x | 24 h, zapętlone | bez końca |

```powershell
.\scenario\run_scenario.ps1 -Preset ciagly -Background   # start w tle
.\scenario\run_scenario.ps1 -Stop                        # zatrzymanie
.\scenario\run_scenario.ps1 -ResetOnly                   # wyczyszczenie tabel
```

Zweryfikowany pełny cykl: **82 212 zdarzeń w 24,0 min** bez zerwania odtwarzania. To okno jest
wyjątkowo gęste (~57 zdarzeń/s), bo `TelecomCoverage` raportuje 2477 gmin co godzinę sceny.

## 7. Reguły alertowe (8) i zweryfikowane trafienia

Wszystkie funkcje zwracają ten sam kontrakt kolumn (`alert_rule`, `alert_severity`, `alert_ts`,
`alert_key`, `current_value`, `threshold_value`, `spo`, `message`).

| Funkcja KQL | Próg | Trafienia | SPO |
|---|---|---|---|
| `alert_izz_critical` | IZŻ ≥ 75 | 25 gmin | SPO-12, SPO-5 |
| `alert_care_facility_autonomy` | autonomia < 2 h | 35 placówek | SPO-12 |
| `alert_priority_person_nocontact` | brak wizyty > 6 h akcji | 50 osób | SPO-12 |
| `alert_severe_cold_nopower` | odczuwalna < −20 °C bez prądu | 50 gmin | SPO-3 |
| `alert_heating_point_full` | zapełnienie ≥ 95% | 1 punkt | SPO-12 |
| `alert_telecom_blackout` | pokrycie < 20% | 50 gmin | SPO-3 |
| `alert_delivery_low` | dostarczalnosć < 60% | 50 gmin | SPO-3 |
| `alert_cascade_detected` | +50 tys. odbiorców w 2 h akcji | 8 okien | SPO-12 |

Reguły z listami gmin i osób są ucięte do 50 pozycji posortowanych wg pilności. Bez tego
`alert_care_facility_autonomy` zwracała 481 placówek, a `alert_telecom_blackout` 234 gminy —
technicznie poprawnie, ale bezużytecznie jako materiał na odprawę.

## 8. Napotkane problemy i rozwiązania

| Problem | Rozwiązanie |
|---|---|
| `.alter table ... policy retention softdelete = 30d recoverability = enabled` → HTTP 400 | Fabric Eventhouse przyjmuje wyłącznie zapis JSON: `policy retention "{\"SoftDeletePeriod\":\"30.00:00:00\",\"Recoverability\":\"Enabled\"}"` |
| `CareFacilityAutonomyState` → `General_BadRequest` bez wskazania miejsca | KQL nie pozwala odwołać się w `extend` do kolumny tworzonej w tym samym kroku — rozbite na dwa `extend` |
| Notatnik `03_dynamic_risk` → `CANNOT_INFER_EMPTY_SCHEMA`, przy 181 gminach z awarią w Eventhouse | Generator zapisuje czas bez sekund (`2026-01-14T12:12+02:00`); Spark `to_timestamp` bez wzorca zwraca dla tego `null` **po cichu**. Loader używa teraz `coalesce()` po liście wzorców i asercji `event_time IS NOT NULL` |
| Fabric Jobs API nie zwraca treści wyjątku z notatnika (tylko „System cancelled the Spark session") | `deploy\debug_notebook.ps1` — wrapper wykonujący kod notatnika w `try/except` i zapisujący traceback do `Files/_debug/` w OneLake |
| Odtwarzanie przerywane po 0,3 min przez `WinError 10054` | `RemoteDisconnected` nie jest `URLError`, więc leciał poza pętlę ponawiania — dodana gałąź `except (OSError, http.client.HTTPException)` |
| Kafelki SPO-3 (18, 19) puste w oknie live | Ostrzeganie SPO-3 poprzedza kaskadę i wypada poza ruchome okno — te dwa kafelki liczą bilans całej akcji, bez filtru czasu |

## 9. Kroki pozostające do wykonania

1. **Model semantyczny i raport Power BI** — `report\REPORT_SPEC.md`, `MODEL.md`. Uwaga: `MODEL.md`
   zakłada tabelę `dim_date_time`, której notatniki nie generują (wymaga parametru wdrożeniowego D0)
   — do rozstrzygnięcia przy budowie modelu.
2. **Data Agent** — instrukcje i przykładowe pytania w `ai\DATA_AGENT.md`.
3. **Fabric App / Rayfin** — specyfikacja `fabric-app\APP_SPEC.md`, prompt `fabric-app\RAYFIN_PROMPT.md`.
4. **Powiadomienia Activatora** — reguły KQL działają; kanały powiadomień dokonfigurować w UI
   wg `activator\RULES.md`.
