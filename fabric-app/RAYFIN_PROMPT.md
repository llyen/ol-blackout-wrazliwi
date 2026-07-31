# Prompt Rayfin / Fabric Apps

Wygeneruj aplikację Fabric App po polsku pod nazwą „Tarcza Zimowa — Ochrona Ludności Wrażliwej”. Kontekst: krajowy scenariusz MRÓZ STYCZEŃ, zagrożenia KPZK `Z19` i `Z07`, wtórnie `Z12` i `Z01`. Celem jest ochrona osób wrażliwych podczas blackoutu: seniorzy samotni, pacjenci tlenoterapii, dializowani, DPS/ZOL, noclegownie, gospodarstwa z ogrzewaniem elektrycznym i gminy bez łączności.

Użyj danych: `dynamic_risk_latest(gmina_code, gmina_name, voivodeship_code, iwl_score, izz_score, life_threat_level, vulnerable_without_power, hours_without_power, coverage_pct, feels_like_c)`, `critical_gminas_latest`, `selected_heating_points(heating_point_id, gmina_code, capacity, effective_daily_capacity, generator_assigned, covered_vulnerable_est)`, `welfare_check_queue(person_token, category, gmina_code, priority_score, medical_device_autonomy_hours, age_band, is_living_alone)`, `welfare_check_routes`, `dim_heating_point`, `dim_generator_stock`, `dim_care_facility`, `alert_delivery`, `telecom_coverage`.

Zbuduj 5 ekranów:

1. **Decydent krajowy** — mapa gmin IZŻ, KPI: 14 gmin krytycznych, 317719 osób wrażliwych bez zasilania, rekomendacje i przyciski `zwołaj RZZK`, `uruchom rezerwy`, `przygotuj SPO-5`.
2. **Wojewoda** — plan punktów i agregatów; pokaż 80 punktów, 29 agregatów, pokrycie 36.7% vs 13.1%. Akcje: zatwierdź, zmień, poproś o zasób.
3. **Gmina/OSP** — lista wizyt, trasa, formularz wyniku. Wymagaj trybu offline: lokalny cache, kolejka synchronizacji, konflikt wersji.
4. **Punkt grzewczy** — checklista otwarcia, obłożenie, potrzeby, agregat, raport co 2h.
5. **Komunikacja SPO-3** — generator komunikatu, kanały RSO/SMS/local_radio, monitoring dostarczenia, retry dla gmin <60%.

Role: `RCB`, `Voivode`, `Gmina`, `OSP_Volunteer`, `MedicalCoordinator`. RLS po `voivodeship_code` i `gmina_code`. Dane `fact_priority_persons` oznacz jako Highly Confidential, maskuj kontakt, nie pozwalaj eksportować list osobowych. Interfejs ma być po polsku, styl operacyjny, wysoki kontrast, kolory zgodne z poziomami ryzyka: monitoring, elevated, high, critical. Każdy ekran ma mieć tooltip „dlaczego” z czynnikami IWL/IZŻ.

Write-back: utwórz tabele `national_decisions`, `generator_assignments`, `welfare_visit_results`, `heating_point_reports`, `alert_campaigns`. Wszystkie zapisy mają mieć `created_by`, `created_at`, `source_role`, `offline_sync_id`, `audit_hash`. Waliduj zakresy: obłożenie 0–capacity, moc agregatu >0, wynik wizyty ze słownika, komunikat SPO-3 160–600 znaków i obowiązkowo lokalizacja punktu pomocy.

Zasady ochrony danych: domyślnie agregaty; lista osób tylko dla przydzielonego zespołu i gminy; koordynator medyczny widzi kategorię i autonomię, nie pełny profil. Dodaj komunikaty odmowy przy próbie dostępu poza rolą. Wszystkie błędy pokaż użytkownikowi prostym językiem: „Nie masz dostępu do tej gminy”, „Brak sieci — zapisano offline”, „Wymagany komentarz przy ewakuacji”.

Wymagania UX: używaj prostego języka, dużych kafli i krótkich etykiet. Nie używaj żargonu analitycznego w widokach terenowych. Każda rekomendacja ma mieć przycisk „dlaczego?” pokazujący czynniki: IWL, godziny bez prądu, temperatura odczuwalna, łączność, czas dojazdu. Dodaj pasek „ostatnia synchronizacja” oraz ostrzeżenie, gdy dane są starsze niż 30 minut.

Wymagania dostępności: wysoki kontrast, obsługa klawiatury, czytelne statusy nieoparte wyłącznie na kolorze, tryb dużej czcionki dla dyżurnych i możliwość wydruku listy zadań. Dla OSP dodaj uproszczony tryb mobilny: trzy przyciski wyniku wizyty, notatka głosowa opcjonalnie jako tekst po transkrypcji, brak złożonych wykresów.

Wymagania bezpieczeństwa: żadnych sekretów w aplikacji, połączenia przez Managed Identity, maskowanie danych kontaktowych, blokada screenów eksportowych dla ról terenowych, audyt każdej akcji. Jeżeli użytkownik pyta o dane spoza swojej gminy, pokaż odmowę i link do procedury eskalacji przez wojewodę.

Wygeneruj także pusty model tabel write-back z kolumnami audytu i przykładowe formularze walidacji. Nie generuj przykładowych prawdziwych danych osobowych; jeśli potrzebny przykład, użyj tokenów `PRIO-00001` i fikcyjnych etykiet.

Dodaj komponent „Centrum decyzji” z listą rekomendacji: otwórz punkt grzewczy, wyślij agregat, ponów komunikat, skieruj OSP, eskaluj do wojewody. Każda rekomendacja ma status `draft/pending_approval/approved/rejected/done`, pole uzasadnienia i przycisk „pokaż dane źródłowe”. W widoku decydenta krajowego nie pokazuj danych osobowych; jeśli rekomendacja wynika z osób priorytetowych, pokaż tylko liczbę i kategorie.

Dodaj komponent „Symulacja what-if” z trzema kontrolkami: awaria +12h, temperatura -5°C, agregaty -30%. Wynik pokaż jako zmianę liczby gmin krytycznych 14 → 104 oraz listę gmin, które wchodzą do progu krytycznego. Przycisk „utwórz wariant planu” tworzy rekord write-back, ale nie zmienia planu bazowego bez akceptacji wojewody.
