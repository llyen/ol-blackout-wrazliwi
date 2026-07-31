# Model semantyczny

Model ma układ gwiazdy z centralną geografią. `dim_voivodeship` filtruje `dim_powiat`, a `dim_powiat` filtruje `dim_gmina`. Fakty i wyniki analityczne łączą się przez `gmina_code`, a pogoda przez `powiat_code`. Kierunek filtrowania: jednokierunkowy z wymiarów do faktów. Wyjątek: strony operacyjne mogą użyć ograniczonych relacji dwukierunkowych tylko w tabelach pomocniczych tras.

## Tabele faktów i wyników

`fact_population_vulnerability` jest faktem agregatowym per gmina. `fact_priority_persons` jest faktem operacyjnym o najwyższej wrażliwości i musi mieć RLS. `dynamic_risk_latest`, `critical_gminas_latest`, `selected_heating_points`, `welfare_check_queue`, `welfare_check_routes`, `whatif_extended_outage` to tabele wynikowe notebooków.

## Tabela dat

Utwórz `dim_date_time` z zakresem D-2…D+7, kolumnami `date`, `hour`, `day_offset`, `demo_phase`, `is_d0`. Relacje do strumieni po `event_time` są nieaktywne w modelu importowym i aktywowane miarami `USERELATIONSHIP`, albo realizowane w KQL dla dashboardu real-time.

## Hierarchie

Hierarchia geograficzna: `voivodeship_name` → `powiat_name` → `gmina_name`. Hierarchia ryzyka: `life_threat_level` → `izz_score` → `main_driver`. Hierarchia operacyjna: `target_type` → `generator_id` → `dispatch_id`.

## RLS

Role: `RCB_National` bez ograniczenia agregatów; `Voivode` filtr `dim_gmina[voivodeship_code] IN USERPRINCIPALNAME mapping`; `Gmina` filtr `gmina_code`; `OSP_Volunteer` przez tabelę przydziałów wizyt; `MedicalCoordinator` widzi kategorię i autonomię, ale nie eksportuje kontaktów.

## Zasady modelowania

Nie łącz bezpośrednio tabel indywidualnych z raportem krajowym. Miary krajowe muszą bazować na agregatach. Dane osobowe/pseudonimowane są dostępne tylko na stronach operacyjnych i w Fabric App. Wszystkie relacje po kodach TERYT traktuj jako tekst.

## Relacje szczegółowe

- `dim_voivodeship[voivodeship_code]` 1:* `dim_powiat[voivodeship_code]`.
- `dim_powiat[powiat_code]` 1:* `dim_gmina[powiat_code]`.
- `dim_gmina[gmina_code]` 1:1 `fact_population_vulnerability[gmina_code]`.
- `dim_gmina[gmina_code]` 1:* `dynamic_risk_latest[gmina_code]`, `selected_heating_points[gmina_code]`, `welfare_check_queue[gmina_code]`, `alert_delivery[gmina_code]`.
- `dim_generator_stock[generator_id]` 1:* `generator_dispatch[generator_id]`.
- `dim_heating_point[heating_point_id]` 1:* `heating_point_status[heating_point_id]`.

## Jakość danych

W modelu dodaj kolumny techniczne: `data_source`, `snapshot_time`, `is_synthetic`. Dla pól kodowych ustaw kategorię danych jako tekst. Nie sumuj procentów bez ważenia populacją. W modelu krajowym ukryj kolumny techniczne, które nie są potrzebne odbiorcy biznesowemu, ale pozostaw je dla drill-through i audytu.
