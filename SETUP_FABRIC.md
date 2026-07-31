# Setup Fabric — Tarcza Zimowa

Poniższa instrukcja zakłada Microsoft Fabric z capacity F2+ oraz repo lokalne `C:\repos\OchronaLudnosci\ol-blackout-wrazliwi`. Nazwy techniczne są celowo stabilne, żeby prowadzący demo i zespół techniczny mówili o tych samych elementach.

## 1. Workspace

**Cel:** utworzyć wspólny obszar demo. **Czynności:** w Fabric wybierz `New workspace`, nazwa `OL_Tarcza_Zimowa_WS`, przypisz capacity, dodaj grupy Entra: `OL_RCB_Admins`, `OL_Voivodes`, `OL_Gmina_Operators`, `OL_OSP_Field`, `OL_Medical_Coordinators`. **Rezultat:** jeden workspace z kontrolą dostępu. **Czas:** 5–10 min.

## 2. Lakehouse `WinterShield_LH`

**Cel:** przechować rejestry i wyniki notebooków. **Czynności:** utwórz Lakehouse, wgraj `datasets\*.csv`, a po uruchomieniu notebooków także `datasets\derived\*.csv`. Ustal foldery `Files/dimensions`, `Files/streams_raw`, `Tables/derived`. **Rezultat:** tabele wsadowe dostępne dla notebooków i modelu. **Czas:** 10–20 min.

## 3. Eventhouse `WinterShield_KQL`

**Cel:** obsłużyć telemetrię i zapytania real-time. **Czynności:** utwórz Eventhouse i KQL Database, otwórz Queryset, uruchom `kql\01_create_tables.kql`, potem `kql\02_update_policies.kql`. **Rezultat:** tabele `WeatherReadings`, `OutageEvents`, `TelecomCoverage`, `EmergencyCalls`, `HeatingPointStatus`, `GeneratorDispatch`, `WelfareCheck`, `AlertDelivery` oraz funkcje `CurrentOutageByGmina()` i `OutageHoursByGmina()`. **Czas:** 10 min.

## 4. Eventstream `WinterShield_Eventstream`

**Cel:** zasymulować napływ danych. **Czynności:** utwórz Eventstream, dodaj źródło `Custom endpoint` albo Event Hub, nazwij wejścia `weather_readings`, `outage_events`, `emergency_calls`, `telecom_coverage`, ustaw routing do tabel KQL. Skopiuj connection string do zmiennej środowiskowej poza repo. **Rezultat:** strumień przyjmuje zdarzenia. **Czas:** 15–25 min.

## 5. Test lokalny symulatora

**Cel:** sprawdzić format bez poświadczeń. **Czynności:** uruchom `python simulate_realtime.py --dry-run`. **Rezultat:** komunikat `DRY RUN OK` i próbka w `datasets\derived\dry_run_*.jsonl`; wybrane są 735602 zdarzenia z 4 strumieni. **Czas:** 1–2 min.

## 6. Notebooki `01`–`06`

**Cel:** policzyć warstwę decyzyjną. **Czynności:** zaimportuj pliki z `notebooks\` jako Fabric Notebooks lub uruchom lokalnie. Kolejność: `01_load_dimensions`, `02_vulnerability_index`, `03_dynamic_risk`, `04_heating_point_siting`, `05_welfare_check_prioritization`, `06_whatif`. **Rezultat:** `datasets\derived\iwl_by_gmina.csv`, `dynamic_risk_latest.csv`, `critical_gminas_latest.csv`, `selected_heating_points.csv`, `welfare_check_queue.csv`, `welfare_check_routes.csv`, `whatif_extended_outage.csv`. **Czas:** 10–30 min.

## 7. Model semantyczny `WinterShield_SemanticModel`

**Cel:** ujednolicić miary i relacje. **Czynności:** utwórz model z tabel Lakehouse/KQL shortcuts, zastosuj relacje z `semantic-model\MODEL.md`, dodaj miary z `MEASURES.md`, utwórz tabelę dat. **Rezultat:** gotowe miary dla raportu i Fabric App. **Czas:** 30–60 min.

## 8. Raport Power BI `WinterShield_Report`

**Cel:** pokazać warstwę decyzyjną. **Czynności:** zbuduj 6 stron wg `report\REPORT_SPEC.md`: mapa IZŻ, ranking, osoby priorytetowe, punkty i agregaty, SPO-3, what-if. **Rezultat:** raport z drill-through do gminy i filtrami województwo/powiat/gmina/czas. **Czas:** 1–2 h.

## 9. Real-Time Dashboard

**Cel:** widok dla dyżurnego. **Czynności:** w Eventhouse użyj zapytań z `kql\03_dashboard_queries.kql`; dodaj kafle: awarie, telco, 112, punkty grzewcze, alerty, wizyty. **Rezultat:** pulpit aktualizowany z KQL. **Czas:** 30–45 min.

## 10. Data Activator

**Cel:** automatyczne alerty. **Czynności:** odwzoruj reguły z `activator\RULES.md`, połącz z Teams/e-mail/workflow. **Rezultat:** alerty dla przekroczenia IZŻ, placówek z niską autonomią, braku kontaktu, mrozu, pełnych punktów, braku łączności i słabej dostarczalności SPO-3. **Czas:** 45–90 min.

## 11. Data Agent `WinterShield_Agent`

**Cel:** pytania językiem naturalnym. **Czynności:** wklej instrukcje z `ai\DATA_AGENT.md`, udostępnij tylko tabele i widoki zgodne z rolą. **Rezultat:** agent odpowiada na pytania o gminy krytyczne, agregaty, tlenoterapię, alerty i what-if. **Czas:** 30–45 min.

## 12. Fabric App / Rayfin

**Cel:** aplikacja operacyjna z write-back. **Czynności:** użyj `fabric-app\RAYFIN_PROMPT.md`, skonfiguruj ekrany z `APP_SPEC.md`, tabele write-back i RLS. **Rezultat:** role RCB, wojewoda, gmina, OSP i medyczny pracują na swoich widokach. **Czas:** 1–2 dni dla pełnego dopracowania UX.

## 13. RLS i etykiety wrażliwości

**Cel:** ochrona danych. **Czynności:** przypisz `Confidential` do placówek i agregatów opieki, `Highly Confidential` do `fact_priority_persons`; ustaw RLS po `voivodeship_code` i `gmina_code`; włącz audyt. **Rezultat:** poziom krajowy widzi agregaty, teren widzi tylko własny zakres. **Czas:** 1–2 h.

## Lista kontrolna „czy działa”

1. `python generate_datasets.py` kończy się bez błędów.
2. `datasets\README.md` pokazuje rekordy dla każdego pliku.
3. Notebook `02` tworzy `iwl_summary.json`.
4. Notebook `03` pokazuje 14 gmin krytycznych.
5. Notebook `04` pokazuje 36,7% pokrycia zoptymalizowanego.
6. Notebook `05` tworzy kolejkę 500 osób.
7. Notebook `06` pokazuje what-if 14 → 104.
8. `simulate_realtime.py --dry-run` pokazuje `DRY RUN OK`.
9. KQL `CurrentOutageByGmina()` zwraca rekordy.
10. Power BI pokazuje miary bez błędów.
11. RLS wojewody ogranicza dane do województwa.
12. Rola OSP nie widzi danych spoza swojej gminy.
13. Activator generuje alert testowy.
14. Data Agent odmawia ujawniania danych konkretnej osoby.

## Rozwiązywanie problemów

1. **Brak `azure-eventhub`:** użyj `--dry-run`; import SDK jest leniwy i nie jest potrzebny offline.
2. **Błąd kodowania w konsoli Windows:** ustaw `$env:PYTHONIOENCODING='utf-8'`.
3. **Brak wyników w `derived`:** uruchom notebooki w kolejności 02→06.
4. **KQL nie widzi tabel:** najpierw uruchom `01_create_tables.kql` w właściwej bazie KQL.
5. **RLS filtruje za dużo:** sprawdź typy `gmina_code` i `voivodeship_code`; powinny być traktowane jako tekst/kody, nie liczby biznesowe.
6. **Eventstream nie routuje:** sprawdź mapowanie nazw pól `event_time`, `gmina_code`, `powiat_code` i typów datetime.
7. **Raport wolno działa:** agreguj strumienie w KQL i importuj tylko wyniki dla Power BI.
8. **Aplikacja offline nie synchronizuje:** sprawdź kolejkę write-back i konflikt wersji rekordu.

## Harmonogram minimalnego uruchomienia pilotażowego

Dzień 1: workspace, Lakehouse, Eventhouse, import danych syntetycznych i uruchomienie KQL. Dzień 2: notebooki i tabele derived. Dzień 3: model semantyczny i raport. Dzień 4: Activator i Data Agent. Dzień 5: Fabric App, RLS, test ról i próba generalna. W realnym wdrożeniu harmonogram wydłuża się głównie przez uzgodnienia prawne, integracje z OSD/NFZ/IMGW i testy bezpieczeństwa, a nie przez samo zbudowanie artefaktów Fabric.

## Konwencje nazw

Używaj prefiksu `WinterShield_` dla elementów technicznych, `OL_` dla grup i workspace oraz stabilnych nazw tabel. Nie zmieniaj nazw kolumn między Lakehouse, KQL i modelem semantycznym, bo Fabric App i Data Agent powinny korzystać z tych samych kontraktów danych. Każdy element produkcyjny powinien mieć właściciela, opis, etykietę wrażliwości i link do procedury odtworzenia.
