# Fabric App — „Tarcza Zimowa — Ochrona Ludności Wrażliwej”

## Założenia

Aplikacja jest narzędziem operacyjnym, nie tylko raportem. Ma działać dla pięciu ról: `RCB`, `Voivode`, `Gmina`, `OSP_Volunteer`, `MedicalCoordinator`. Każdy ekran ma własny zakres danych, RLS, write-back i tryb offline tam, gdzie użytkownik może pracować w terenie bez zasięgu.

## Ekran 1 — Decydent krajowy

**Cel:** szybki obraz kraju i przesłanki eskalacji RZZK/SPO-5. **Użytkownik:** RCB, minister, dyrektor RCB.  
**Wireframe:** lewa strona mapa gmin IZŻ; góra KPI: gminy krytyczne, osoby wrażliwe bez zasilania, skuteczność SPO-3, aktywne alerty; prawa strona rekomendacje.  
**Pola:** `time_snapshot` datetime wymagane; `voivodeship_filter` multi-select; `critical_only` boolean; `recommendation_status` enum. Walidacja: filtr daty w osi D-2…D+7.  
**Źródła:** `dynamic_risk_latest[gmina_code, izz_score, life_threat_level, vulnerable_without_power, coverage_pct, hours_without_power]`, `critical_gminas_latest`, `alert_delivery`.  
**Akcje write-back:** `create_national_decision(decision_type, scope, justification)` do tabeli `national_decisions`. Efekt: audyt decyzji i powiadomienie wojewodów.  
**Przejścia:** do ekranu wojewody po kliknięciu województwa; do SPO-3 po kliknięciu niskiej dostarczalności.  
**Uprawnienia:** tylko agregaty; brak list osób.  
**Powiadomienia:** alert przy przekroczeniu IZŻ i kaskadzie. **Offline:** widok read-only z ostatnim snapshotem.

## Ekran 2 — Wojewoda

**Cel:** zatwierdzić plan punktów grzewczych i agregatów. **Użytkownik:** wojewoda, WCZK.  
**Wireframe:** mapa województwa, tabela `selected_heating_points`, panel agregatów, przyciski `Approve`, `Modify`, `Request more`.  
**Pola:** `heating_point_id` string wymagany; `generator_id` string opcjonalny; `power_kw` number >0; `eta_minutes` integer 0–1440; `decision_comment` text wymagany przy modyfikacji.  
**Źródła:** `selected_heating_points`, `dim_heating_point`, `dim_generator_stock`, `dynamic_risk_latest`.  
**Write-back:** `generator_assignments(assignment_id, generator_id, heating_point_id, gmina_code, status, approved_by, approved_at, comment)`. Efekt: zmiana statusu planu i powiadomienie gminy.  
**Przejścia:** do gminy po kliknięciu punktu; do alertu przy braku mocy.  
**Uprawnienia:** wojewoda widzi tylko `voivodeship_code`. **Offline:** możliwość eksportu paczki planu do CSV/PDF.

## Ekran 3 — Gmina/OSP

**Cel:** realizować wizyty kontrolne. **Użytkownik:** wójt, dyżurny gminy, druh OSP.  
**Wireframe:** lista priorytetowa, mapa trasy, karta osoby z minimalnymi danymi, formularz wyniku.  
**Pola:** `person_token` string wymagany; `visit_result` enum `contact_confirmed/no_contact/evacuation/generator_needed`; `visit_time` datetime; `team_id` string; `notes` text max 500; `offline_sync_id` GUID. Walidacja: nie można wysłać wyniku dla osoby spoza przydziału; przy `evacuation` wymagane miejsce docelowe.  
**Źródła:** `welfare_check_queue`, `welfare_check_routes`, `fact_priority_persons[person_token, category, age_band, medical_device_autonomy_hours]`, `dynamic_risk_latest`.  
**Write-back:** `welfare_visit_results`. Efekt: status osoby i powiadomienie koordynatora.  
**Offline:** krytyczne. Aplikacja zapisuje ostatnią kolejkę, trasę i słowniki lokalnie. Wyniki trafiają do kolejki synchronizacji z konfliktem `last_write_wins` tylko dla statusu technicznego; konflikty medyczne wymagają ręcznej akceptacji.

## Ekran 4 — Punkt grzewczy

**Cel:** uruchomić i raportować punkt. **Użytkownik:** gmina, OSP, zarządca szkoły/remizy.  
**Wireframe:** checklista otwarcia, licznik obłożenia, potrzeby, status agregatu, historia raportów.  
**Pola:** `heating_point_id`; `status` enum `planned/open/full/closed`; `occupancy` integer 0–capacity; `needs_food` boolean; `needs_medical_support` boolean; `needs_generator` boolean; `fuel_hours_remaining` number >=0. Walidacja: obłożenie nie może być ujemne, >capacity wymaga komentarza.  
**Źródła:** `dim_heating_point`, `heating_point_status`, `selected_heating_points`.  
**Write-back:** `heating_point_reports`. Efekt: aktualizacja dashboardu i reguł Activator.  
**Offline:** raport co 2h może być zapisany lokalnie i wysłany po odzyskaniu łączności.

## Ekran 5 — Komunikacja SPO-3

**Cel:** przygotować komunikat i mierzyć dotarcie. **Użytkownik:** RCB, wojewoda, gmina.  
**Wireframe:** wybór gmin, generator treści, kanały, podgląd, wskaźnik dostarczenia, retry.  
**Pola:** `message_text` text 160–600; `channels` multi-select `RSO/SMS/local_radio/WWW/social`; `target_gminas` list; `approval_status`; `language` default `pl-PL`. Walidacja: komunikat musi zawierać miejsce ogrzania, numer alarmowy, zasady bezpieczeństwa CO i godzinę aktualizacji.  
**Źródła:** `alert_delivery`, `dynamic_risk_latest`, `telecom_coverage`, `dim_gmina`.  
**Write-back:** `alert_campaigns`. Efekt: kampania i monitoring dostarczalności.  
**Offline:** możliwość wydruku komunikatu dla OSP, radia lokalnego i tablic ogłoszeń.

## Model tabel write-back

| Tabela | Klucz | Najważniejsze kolumny | Retencja |
|---|---|---|---|
| `national_decisions` | `decision_id` | `decision_type`, `scope`, `justification`, `created_by`, `created_at` | zgodnie z archiwizacją ZK |
| `generator_assignments` | `assignment_id` | `generator_id`, `target_id`, `status`, `eta`, `approved_by` | czas zdarzenia + rozliczenie |
| `welfare_visit_results` | `visit_result_id` | `person_token`, `result`, `team_id`, `offline_sync_id` | minimalna, potem anonimizacja |
| `heating_point_reports` | `report_id` | `occupancy`, `needs_*`, `fuel_hours_remaining` | agregacja po zdarzeniu |
| `alert_campaigns` | `campaign_id` | `message_text`, `channels`, `target_gminas`, `approval_status` | audyt SPO-3 |

## Obsługa błędów

Brak sieci: przejście offline. Brak uprawnień: komunikat z rolą i zakresem RLS. Konflikt write-back: ekran porównania wersji. Brak danych KQL: użycie ostatniego snapshotu Lakehouse. Próba eksportu danych wrażliwych: blokada i zapis audytu. Błąd walidacji: wskazanie pola i procedury naprawczej.

## Tryb offline — szczegóły techniczne

Aplikacja terenowa musi zakładać, że w gminie krytycznej nie ma stabilnej transmisji. Przed wyjazdem zespół pobiera paczkę: przydzielone wizyty, trasy, słowniki wyników, ostatni komunikat SPO-3 i listę punktów grzewczych. Paczka jest szyfrowana i wygasa po określonym czasie. W terenie formularze zapisują się lokalnie z `offline_sync_id`, znacznikiem czasu urządzenia i statusem `pending_sync`. Po odzyskaniu łączności aplikacja wysyła zmiany, pobiera konflikty i pokazuje operatorowi tylko te rekordy, które wymagają decyzji. Jeżeli telefon zostanie utracony, administrator unieważnia paczkę i token urządzenia.

## Uprawnienia per rola — macierz skrócona

| Funkcja | RCB | Voivode | Gmina | OSP | MedicalCoordinator |
|---|---|---|---|---|---|
| Widok krajowy agregatów | tak | tylko woj. | nie | nie | agregaty medyczne |
| Plan agregatów | odczyt | zapis | odczyt lokalny | nie | odczyt medyczny |
| Lista osób | nie | agregat | własna gmina | przydzielone | kategorie medyczne |
| Wynik wizyty | nie | odczyt | zapis/odczyt | zapis | odczyt |
| Kampania SPO-3 | zapis krajowy | zapis woj. | zapis lokalny | odczyt | odczyt |
| Eksport danych indywidualnych | nie | nie | ograniczony | nie | nie |

## Testy akceptacyjne aplikacji

Przed demo sprawdź: RCB nie widzi kontaktów; OSP bez sieci może zapisać wynik; wojewoda może zmienić przydział agregatu z komentarzem; punkt grzewczy nie przyjmie ujemnego obłożenia; kampania SPO-3 nie przejdzie bez treści komunikatu; wszystkie akcje tworzą rekord audytu.
