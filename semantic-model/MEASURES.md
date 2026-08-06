# Miary DAX

Miary modelu `OL_BLK_SemanticModel`, wygenerowane z `deploy/model_spec.py`.
Plik powstaje skryptem `deploy/export_measures.py` — nie edytuj go ręcznie,
bo przy najbliższym wdrożeniu zmiany zostaną nadpisane.
Łącznie 73 miar w 21 tabelach.


## `alert_delivery`

### Wiadomości wysłane

```dax
Wiadomości wysłane =
SUM ( alert_delivery[messages_sent] )
```

Format: liczba całkowita.

### Skuteczność alertów %

```dax
Skuteczność alertów % =
DIVIDE ( SUM ( alert_delivery[messages_delivered] ),
    SUM ( alert_delivery[messages_sent] ) )
```

Format: procent.

### Otwarcia alertów %

```dax
Otwarcia alertów % =
DIVIDE ( SUM ( alert_delivery[messages_opened] ),
    SUM ( alert_delivery[messages_delivered] ) )
```

Format: procent.

### Gminy z dostarczeniem poniżej 60%

```dax
Gminy z dostarczeniem poniżej 60% =
COUNTROWS (
    FILTER (
        SUMMARIZE ( alert_delivery, alert_delivery[gmina_code],
            "Skutecznosc", [Skuteczność alertów %] ),
        [Skutecznosc] < 0.6
    )
)
```

Format: liczba całkowita.

## `critical_crossing_times`

### Gminy z przekroczeniem progu

```dax
Gminy z przekroczeniem progu =
COUNTROWS ( critical_crossing_times )
```

Format: liczba całkowita.

## `dim_care_facility`

### Placówki opiekuńcze

```dax
Placówki opiekuńcze =
COUNTROWS ( dim_care_facility )
```

Format: liczba całkowita.

### Podopieczni w placówkach

```dax
Podopieczni w placówkach =
SUM ( dim_care_facility[current_occupancy] )
```

Format: liczba całkowita.

### Placówki bez zapasu zasilania

```dax
Placówki bez zapasu zasilania =
CALCULATE ( COUNTROWS ( dim_care_facility ),
    FILTER ( dim_care_facility,
        dim_care_facility[has_generator] = FALSE ()
            || dim_care_facility[generator_autonomy_hours] < 2 ) )
```

Format: liczba całkowita.

### Zapotrzebowanie mocy placówek (kW)

```dax
Zapotrzebowanie mocy placówek (kW) =
SUM ( dim_care_facility[power_need_kw] )
```

Format: liczba całkowita.

## `dim_generator_stock`

### Agregaty w magazynach

```dax
Agregaty w magazynach =
COUNTROWS ( dim_generator_stock )
```

Format: liczba całkowita.

### Agregaty dostępne

```dax
Agregaty dostępne =
CALCULATE ( COUNTROWS ( dim_generator_stock ), dim_generator_stock[status] = "available" )
```

Format: liczba całkowita.

### Moc dostępna (kW)

```dax
Moc dostępna (kW) =
CALCULATE ( SUM ( dim_generator_stock[power_kw] ),
    dim_generator_stock[status] = "available" )
```

Format: liczba całkowita.

## `dim_gmina`

### Gminy w rejestrze

```dax
Gminy w rejestrze =
COUNTROWS ( dim_gmina )
```

Format: liczba całkowita.

### Ludność rejestru

```dax
Ludność rejestru =
SUM ( dim_gmina[population] )
```

Format: liczba całkowita.

## `dim_heating_point`

### Punkty grzewcze w rejestrze

```dax
Punkty grzewcze w rejestrze =
COUNTROWS ( dim_heating_point )
```

Format: liczba całkowita.

### Punkty z własnym zasilaniem

```dax
Punkty z własnym zasilaniem =
CALCULATE ( COUNTROWS ( dim_heating_point ),
    dim_heating_point[has_generator] = TRUE () )
```

Format: liczba całkowita.

## `dynamic_risk_latest`

### Osoby wrażliwe bez zasilania

```dax
Osoby wrażliwe bez zasilania =
SUM ( dynamic_risk_latest[vulnerable_without_power] )
```

Format: liczba całkowita.

### Gminy krytyczne

```dax
Gminy krytyczne =
CALCULATE ( DISTINCTCOUNT ( dynamic_risk_latest[gmina_code] ),
    dynamic_risk_latest[life_threat_level] = "critical" )
```

Format: liczba całkowita.

### Gminy monitorowane

```dax
Gminy monitorowane =
DISTINCTCOUNT ( dynamic_risk_latest[gmina_code] )
```

Format: liczba całkowita.

### Średni IZŻ

```dax
Średni IZŻ =
AVERAGE ( dynamic_risk_latest[izz_score] )
```

Format: liczba z jednym miejscem.

### Maksymalny IZŻ

```dax
Maksymalny IZŻ =
MAX ( dynamic_risk_latest[izz_score] )
```

Format: liczba z jednym miejscem.

### Osobogodziny bez zasilania

```dax
Osobogodziny bez zasilania =
SUMX ( dynamic_risk_latest,
    dynamic_risk_latest[vulnerable_without_power]
        * dynamic_risk_latest[hours_without_power] )
```

Format: liczba całkowita.

### Odbiorcy bez zasilania

```dax
Odbiorcy bez zasilania =
SUM ( dynamic_risk_latest[customers_without_power] )
```

Format: liczba całkowita.

### Najdłuższa przerwa (h)

```dax
Najdłuższa przerwa (h) =
MAX ( dynamic_risk_latest[hours_without_power] )
```

Format: liczba z jednym miejscem.

### Odczuwalna temperatura (°C)

```dax
Odczuwalna temperatura (°C) =
AVERAGE ( dynamic_risk_latest[feels_like_c] )
```

Format: liczba z jednym miejscem.

### Główny czynnik ryzyka

```dax
Główny czynnik ryzyka =
VAR T = AVERAGE ( dynamic_risk_latest[temp_component] )
VAR O = AVERAGE ( dynamic_risk_latest[outage_component] )
VAR C = AVERAGE ( dynamic_risk_latest[telecom_component] )
VAR R = AVERAGE ( dynamic_risk_latest[rescue_component] )
VAR Max1 = MAX ( MAX ( T, O ), MAX ( C, R ) )
RETURN SWITCH ( TRUE (),
    Max1 = T, "mróz",
    Max1 = O, "brak zasilania",
    Max1 = C, "łączność",
    "czas dojazdu" )
```

Format: tekst.

## `emergency_calls`

### Zgłoszenia alarmowe

```dax
Zgłoszenia alarmowe =
COUNTROWS ( emergency_calls )
```

Format: liczba całkowita.

### Zgłoszenia P1

```dax
Zgłoszenia P1 =
CALCULATE ( COUNTROWS ( emergency_calls ), emergency_calls[priority] = "P1" )
```

Format: liczba całkowita.

## `fact_population_vulnerability`

### Populacja objęta analizą

```dax
Populacja objęta analizą =
SUM ( fact_population_vulnerability[population] )
```

Format: liczba całkowita.

### Szacowana populacja wrażliwa

```dax
Szacowana populacja wrażliwa =
SUM ( fact_population_vulnerability[vulnerable_population_est] )
```

Format: liczba całkowita.

### Udział populacji wrażliwej %

```dax
Udział populacji wrażliwej % =
DIVIDE ( [Szacowana populacja wrażliwa], [Populacja objęta analizą] )
```

Format: procent.

## `fact_priority_persons`

### Osoby priorytetowe

```dax
Osoby priorytetowe =
DISTINCTCOUNT ( fact_priority_persons[person_token] )
```

Format: liczba całkowita.

### Kontakt priorytetowy potwierdzony %

```dax
Kontakt priorytetowy potwierdzony % =
DIVIDE ( [Kontakt potwierdzony], [Osoby priorytetowe] )
```

Format: procent.

## `generator_dispatch`

### Wydania agregatów

```dax
Wydania agregatów =
COUNTROWS ( generator_dispatch )
```

Format: liczba całkowita.

### Moc wydana (kW)

```dax
Moc wydana (kW) =
SUM ( generator_dispatch[power_kw] )
```

Format: liczba całkowita.

## `heating_point_status`

### Zajętość punktów

```dax
Zajętość punktów =
SUM ( heating_point_status[occupancy] )
```

Format: liczba całkowita.

### Pojemność punktów

```dax
Pojemność punktów =
SUM ( heating_point_status[capacity] )
```

Format: liczba całkowita.

### Wypełnienie punktów %

```dax
Wypełnienie punktów % =
DIVIDE ( [Zajętość punktów], [Pojemność punktów] )
```

Format: procent.

### Punkty pełne

```dax
Punkty pełne =
COUNTROWS ( FILTER ( heating_point_status,
    DIVIDE ( heating_point_status[occupancy], heating_point_status[capacity] ) >= 0.95 ) )
```

Format: liczba całkowita.

### Wolne miejsca w punktach

```dax
Wolne miejsca w punktach =
[Pojemność punktów] - [Zajętość punktów]
```

Format: liczba całkowita.

## `iwl_by_gmina`

### Średni IWL

```dax
Średni IWL =
AVERAGE ( iwl_by_gmina[iwl_score] )
```

Format: liczba z jednym miejscem.

### Maksymalny IWL

```dax
Maksymalny IWL =
MAX ( iwl_by_gmina[iwl_score] )
```

Format: liczba z jednym miejscem.

## `outage_events`

### Awarie zgłoszone

```dax
Awarie zgłoszone =
DISTINCTCOUNT ( outage_events[outage_id] )
```

Format: liczba całkowita.

### Awarie nieusunięte

```dax
Awarie nieusunięte =
COALESCE ( COUNTROWS (
    FILTER (
        VALUES ( outage_events[outage_id] ),
        VAR Ostatni = CALCULATE ( MAX ( outage_events[event_time] ) )
        RETURN CALCULATE ( SELECTEDVALUE ( outage_events[status] ),
            outage_events[event_time] = Ostatni ) <> "restored"
    )
), 0 )
```

Format: liczba całkowita.

### Odbiorcy w czynnych awariach

```dax
Odbiorcy w czynnych awariach =
COALESCE ( SUMX (
    VALUES ( outage_events[outage_id] ),
    VAR Ostatni = CALCULATE ( MAX ( outage_events[event_time] ) )
    VAR Stan = CALCULATE ( SELECTEDVALUE ( outage_events[status] ),
        outage_events[event_time] = Ostatni )
    VAR Odbiorcy = CALCULATE ( SELECTEDVALUE ( outage_events[customers_without_power] ),
        outage_events[event_time] = Ostatni )
    RETURN IF ( Stan <> "restored", Odbiorcy )
), 0 )
```

Format: liczba całkowita.

### Szczyt odbiorców bez zasilania

```dax
Szczyt odbiorców bez zasilania =
MAXX ( VALUES ( outage_events[event_time] ),
    CALCULATE ( SUM ( outage_events[customers_without_power] ) ) )
```

Format: liczba całkowita.

### Najgłębszy etap kaskady

```dax
Najgłębszy etap kaskady =
MAX ( outage_events[cascade_stage] )
```

Format: liczba całkowita.

## `selected_heating_points`

### Wybrane punkty grzewcze

```dax
Wybrane punkty grzewcze =
COUNTROWS ( selected_heating_points )
```

Format: liczba całkowita.

### Osoby objęte punktami

```dax
Osoby objęte punktami =
SUM ( selected_heating_points[covered_vulnerable_est] )
```

Format: liczba całkowita.

### Przydzielone agregaty

```dax
Przydzielone agregaty =
CALCULATE ( COUNTROWS ( selected_heating_points ),
    selected_heating_points[generator_assigned] = TRUE () )
```

Format: liczba całkowita.

### Przepustowość dobowa punktów

```dax
Przepustowość dobowa punktów =
SUM ( selected_heating_points[effective_daily_capacity] )
```

Format: liczba całkowita.

### Pokrycie punktami grzewczymi %

```dax
Pokrycie punktami grzewczymi % =
DIVIDE ( SUM ( selected_heating_points[covered_vulnerable_est] ),
    SUM ( dynamic_risk_latest[vulnerable_without_power] ) )
```

Format: procent.

### Poprawa pokrycia p.p.

```dax
Poprawa pokrycia p.p. =
( [Pokrycie punktami grzewczymi %] - 0.131 ) * 100
```

Format: liczba z jednym miejscem.

## `telecom_coverage`

### Pokrycie telekomunikacyjne %

```dax
Pokrycie telekomunikacyjne % =
AVERAGE ( telecom_coverage[coverage_pct] )
```

Format: procent.

### Stacje na akumulatorach

```dax
Stacje na akumulatorach =
SUM ( telecom_coverage[bts_on_battery] )
```

Format: liczba całkowita.

### Zapas akumulatorów (h)

```dax
Zapas akumulatorów (h) =
MIN ( telecom_coverage[battery_hours_remaining] )
```

Format: liczba z jednym miejscem.

## `weather_readings`

### Najniższa odczuwalna (°C)

```dax
Najniższa odczuwalna (°C) =
MIN ( weather_readings[feels_like_c] )
```

Format: liczba z jednym miejscem.

### Maksymalny wiatr (km/h)

```dax
Maksymalny wiatr (km/h) =
MAX ( weather_readings[wind_kmh] )
```

Format: liczba z jednym miejscem.

## `welfare_check`

### Wizyty kontrolne

```dax
Wizyty kontrolne =
COUNTROWS ( welfare_check )
```

Format: liczba całkowita.

### Kontakt potwierdzony

```dax
Kontakt potwierdzony =
CALCULATE ( COUNTROWS ( welfare_check ), welfare_check[result] = "contact_confirmed" )
```

Format: liczba całkowita.

### Ewakuacje

```dax
Ewakuacje =
CALCULATE ( COUNTROWS ( welfare_check ), welfare_check[result] = "evacuation" )
```

Format: liczba całkowita.

### Brak kontaktu

```dax
Brak kontaktu =
CALCULATE ( COUNTROWS ( welfare_check ), welfare_check[result] = "no_contact" )
```

Format: liczba całkowita.

### Skuteczność wizyt %

```dax
Skuteczność wizyt % =
DIVIDE ( [Kontakt potwierdzony], [Wizyty kontrolne] )
```

Format: procent.

## `welfare_check_queue`

### Osoby w kolejce wizyt

```dax
Osoby w kolejce wizyt =
COUNTROWS ( welfare_check_queue )
```

Format: liczba całkowita.

### Osoby z autonomią poniżej 4 h

```dax
Osoby z autonomią poniżej 4 h =
COUNTROWS ( FILTER ( welfare_check_queue,
    welfare_check_queue[medical_device_autonomy_hours] < 4 ) )
```

Format: liczba całkowita.

### Osoby samotne w kolejce

```dax
Osoby samotne w kolejce =
CALCULATE ( COUNTROWS ( welfare_check_queue ),
    welfare_check_queue[is_living_alone] = TRUE () )
```

Format: liczba całkowita.

### Najwyższy priorytet wizyty

```dax
Najwyższy priorytet wizyty =
MAX ( welfare_check_queue[priority_score] )
```

Format: liczba z jednym miejscem.

## `welfare_check_routes`

### Zaplanowane wizyty

```dax
Zaplanowane wizyty =
COUNTROWS ( welfare_check_routes )
```

Format: liczba całkowita.

### Zespoły w terenie

```dax
Zespoły w terenie =
DISTINCTCOUNT ( welfare_check_routes[team_id] )
```

Format: liczba całkowita.

### Średni czas dojazdu (min)

```dax
Średni czas dojazdu (min) =
AVERAGE ( welfare_check_routes[eta_min] )
```

Format: liczba z jednym miejscem.

## `whatif_extended_outage`

### Gminy krytyczne w wariancie

```dax
Gminy krytyczne w wariancie =
CALCULATE ( DISTINCTCOUNT ( whatif_extended_outage[gmina_code] ),
    whatif_extended_outage[whatif_izz] >= 75 )
```

Format: liczba całkowita.

### Przyrost gmin krytycznych

```dax
Przyrost gmin krytycznych =
[Gminy krytyczne w wariancie] - [Gminy krytyczne]
```

Format: liczba całkowita.

### IZŻ w wariancie

```dax
IZŻ w wariancie =
AVERAGE ( whatif_extended_outage[whatif_izz] )
```

Format: liczba z jednym miejscem.
