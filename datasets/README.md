# Datasets — Tarcza Zimowa

> ⚠️ **Disclaimer:** wszystkie dane są w 100% syntetyczne, wygenerowane proceduralnie (`generate_datasets.py`, seed=42). Nie są danymi operacyjnymi żadnej instytucji i nie zawierają prawdziwych danych osobowych. `fact_priority_persons.csv` zawiera wyłącznie fikcyjne, pseudonimowane rekordy demonstracyjne. Podejście privacy-by-design: agregacja per gmina, minimalizacja, etykiety wrażliwości, RLS/Purview opisane w dokumentacji.

## Pliki wsadowe CSV

| Plik | Rekordy | Zakres / ziarno | Opis |
|---|---:|---|---|
| `dim_voivodeship.csv` | 16 | `voivodeship_code` | 16 województw, centroidy i oznaczenie osi `MROZ_STYCZEN` dla województw głównych. |
| `dim_powiat.csv` | 380 | `powiat_code` | Syntetyczne powiaty z przypisaniem do województwa i centroidem. |
| `dim_gmina.csv` | 2477 | `gmina_code` | Syntetyczne gminy TERYT-like: typ, populacja, gęstość, współrzędne, wiejskość. |
| `dim_vulnerability_factors.csv` | 13 | `factor_code` | Katalog czynników IWL z wagami i metodą normalizacji. |
| `fact_population_vulnerability.csv` | 2477 | `gmina_code` | Agregatowe wskaźniki wrażliwości per gmina; bez danych osobowych. |
| `fact_priority_persons.csv` | 1250 | `person_token` | Fikcyjna lista osób priorytetowych: kategoria, gmina, autonomia, fikcyjny kontakt i etykieta wrażliwości. |
| `dim_care_facility.csv` | 900 | `facility_id` | DPS, ZOL, szpitale, hospicja, noclegownie i schroniska; pojemność, agregat, autonomia, zapotrzebowanie mocy. |
| `dim_heating_point.csv` | 500 | `heating_point_id` | Potencjalne punkty grzewcze: szkoły, OSP, świetlice, hale; pojemność i dostępność zasilania/ciepła. |
| `dim_grid_asset.csv` | 600 | `grid_asset_id` | Elementy sieci: GPZ, linie, transformatory, obsługiwane gminy i podatność na oblodzenie. |
| `dim_generator_stock.csv` | 420 | `generator_id` | Agregaty w magazynach: moc, paliwo, mobilność, status i lokalizacja. |

## Strumienie JSONL

| Plik | Rekordy | Zakres czasowy | Ziarno | Opis |
|---|---:|---|---|---|
| `weather_readings.jsonl` | 201020 | D-2…D+7, co 30 min | `event_time + powiat_code` | Temperatura, odczuwalna, wiatr, śnieg i oblodzenie. |
| `outage_events.jsonl` | 6650 | D0…D+7, aktualizacje ok. 2h | `event_time + outage_id` | Kaskadowe awarie sieci w 3 etapach, ETA przywrócenia i odbiorcy bez prądu. |
| `telecom_coverage.jsonl` | 522647 | D0…D+7, co 1h | `event_time + gmina_code` | Pokrycie telco; BTS-y tracą zasięg po 4–8h baterii. |
| `emergency_calls.jsonl` | 5285 | D-2…D+7 | `call_id` | Zgłoszenia 112: wychłodzenie, brak ogrzewania, awaria sprzętu medycznego, pojazdy, welfare check. |
| `heating_point_status.jsonl` | 330 | D0…D+7 | `event_time + heating_point_id` | Otwarcie punktów, obłożenie i potrzeby żywnościowe/medyczne/agregat. |
| `generator_dispatch.jsonl` | 260 | D0…D+7 | `dispatch_id` | Wydania agregatów: cel, gmina, status, moc. |
| `welfare_check.jsonl` | 202 | D0…D+7 | `visit_id` | Wyniki wizyt u fikcyjnych osób priorytetowych. |
| `alert_delivery.jsonl` | 7431 | D0 i okres ostrzegania | `event_time + gmina_code + channel` | Wysyłka i dostarczenie alertów RSO/SMS/radio lokalne, SPO-3. |

## Spójność scenariusza

Awaria kaskaduje w województwach podlaskim, warmińsko-mazurskim, mazowieckim i lubelskim. BTS-y tracą zasięg po wyczerpaniu baterii w oknie 4–8 godzin. Zgłoszenia 112 rosną wraz ze spadkiem temperatury i czasem bez prądu. Autonomia placówek opieki jest syntetyczna i służy regułom Activator oraz decyzjom o agregatach albo ewakuacji.

## `datasets/derived/`

Katalog `derived` zawiera wyniki notebooków używane bezpośrednio w demo:

| Plik | Źródło | Kluczowe liczby |
|---|---|---|
| `iwl_by_gmina.csv`, `iwl_summary.json` | `02_vulnerability_index.py` | IWL: średnia 63.03, P90 79.83, top gmina `2817005`. |
| `dynamic_risk_latest.csv`, `critical_gminas_latest.csv`, `dynamic_risk_summary.json` | `03_dynamic_risk.py` | 14 gmin krytycznych, 317719 osób wrażliwych bez zasilania, max 59.3 h bez prądu. |
| `critical_crossing_times.csv` | `03_dynamic_risk.py` | Pierwszy moment przekroczenia progu krytycznego per gmina krytyczna. |
| `selected_heating_points.csv`, `heating_point_optimization_summary.json` | `04_heating_point_siting.py` | 80 punktów, 29 agregatów, pokrycie 36.7% vs 13.1%, poprawa +23.6 p.p. |
| `welfare_check_queue.csv`, `welfare_check_routes.csv`, `welfare_check_summary.json` | `05_welfare_check_prioritization.py` | Kolejka 500 osób, 147 wizyt w pierwszej zmianie, 16 zespołów/obszarów. |
| `whatif_extended_outage.csv`, `whatif_summary.json` | `06_whatif.py` | Awaria +12h, temperatura -5°C, agregaty -30%: wzrost 14 → 104 gmin krytycznych. |
| `dry_run_*.jsonl` | `simulate_realtime.py --dry-run` | Próbka zdarzeń offline bez poświadczeń i bez `azure-eventhub`. |

Te liczby są cytowane w `README.md`, `DEMO_SCRIPT.md`, specyfikacji raportu i aplikacji. Po ponownym wygenerowaniu danych należy uruchomić notebooki oraz `update_results.py`, aby zsynchronizować dokumentację z wynikami.

## ⚠️ Pliki danych spoza repozytorium

Najwieksze pliki strumieniowe nie sa wersjonowane w Git (limity GitHub, czas klonowania).
Sa **w pelni odtwarzalne** — generator uzywa `seed=42`:

```powershell
python generate_datasets.py
```

Pliki wylaczone z repozytorium:
- `telecom_coverage.jsonl` (~73 MB)
- `weather_readings.jsonl` (~30 MB)

