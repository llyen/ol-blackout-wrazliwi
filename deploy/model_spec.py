"""Miary, relacje i tabele ukryte modelu OL_BLK_SemanticModel.

Wydzielone ze skryptu wdrożeniowego, bo to jedyna część różniąca się między
scenariuszami — mechanika budowy TMDL jest wspólna z pozostałymi repozytoriami.

Miary nazwane po polsku, bo trafiają wprost do raportu i do odpowiedzi Data
Agenta, czyli przed oczy decydenta, a nie inżyniera. Nazwy techniczne tabel
i kolumn pozostają angielskie zgodnie z konwencją programu.
"""

MEASURES = {
    "dynamic_risk_latest": [
        ("Osoby wrażliwe bez zasilania",
         "SUM ( dynamic_risk_latest[vulnerable_without_power] )", "#,0"),
        ("Gminy krytyczne",
         'CALCULATE ( DISTINCTCOUNT ( dynamic_risk_latest[gmina_code] ),\n'
         '    dynamic_risk_latest[life_threat_level] = "critical" )', "#,0"),
        ("Gminy monitorowane", "DISTINCTCOUNT ( dynamic_risk_latest[gmina_code] )", "#,0"),
        ("Średni IZŻ", "AVERAGE ( dynamic_risk_latest[izz_score] )", "#,0.0"),
        ("Maksymalny IZŻ", "MAX ( dynamic_risk_latest[izz_score] )", "#,0.0"),
        # Osobogodziny to jedyna miara, która łączy skalę z czasem trwania.
        # Dwie gminy o tym samym IZŻ różnią się tym, jak długo już tak stoją.
        ("Osobogodziny bez zasilania",
         "SUMX ( dynamic_risk_latest,\n"
         "    dynamic_risk_latest[vulnerable_without_power]\n"
         "        * dynamic_risk_latest[hours_without_power] )", "#,0"),
        ("Odbiorcy bez zasilania",
         "SUM ( dynamic_risk_latest[customers_without_power] )", "#,0"),
        ("Najdłuższa przerwa (h)", "MAX ( dynamic_risk_latest[hours_without_power] )", "#,0.0"),
        ("Odczuwalna temperatura (°C)", "AVERAGE ( dynamic_risk_latest[feels_like_c] )", "#,0.0"),
        # Który składnik napędza ryzyko — to decyduje, czy wysyłamy agregat,
        # czy ekipę do ludzi. Bez tego IZŻ jest liczbą bez zalecenia.
        ("Główny czynnik ryzyka",
         "VAR T = AVERAGE ( dynamic_risk_latest[temp_component] )\n"
         "VAR O = AVERAGE ( dynamic_risk_latest[outage_component] )\n"
         "VAR C = AVERAGE ( dynamic_risk_latest[telecom_component] )\n"
         "VAR R = AVERAGE ( dynamic_risk_latest[rescue_component] )\n"
         "VAR Max1 = MAX ( MAX ( T, O ), MAX ( C, R ) )\n"
         "RETURN SWITCH ( TRUE (),\n"
         '    Max1 = T, "mróz",\n'
         '    Max1 = O, "brak zasilania",\n'
         '    Max1 = C, "łączność",\n'
         '    "czas dojazdu" )', None),
    ],
    "selected_heating_points": [
        ("Wybrane punkty grzewcze", "COUNTROWS ( selected_heating_points )", "#,0"),
        ("Osoby objęte punktami",
         "SUM ( selected_heating_points[covered_vulnerable_est] )", "#,0"),
        ("Przydzielone agregaty",
         "CALCULATE ( COUNTROWS ( selected_heating_points ),\n"
         "    selected_heating_points[generator_assigned] = TRUE () )", "#,0"),
        ("Przepustowość dobowa punktów",
         "SUM ( selected_heating_points[effective_daily_capacity] )", "#,0"),
    ],
    "alert_delivery": [
        ("Wiadomości wysłane", "SUM ( alert_delivery[messages_sent] )", "#,0"),
        ("Skuteczność alertów %",
         "DIVIDE ( SUM ( alert_delivery[messages_delivered] ),\n"
         "    SUM ( alert_delivery[messages_sent] ) )", "0.0%"),
        ("Otwarcia alertów %",
         "DIVIDE ( SUM ( alert_delivery[messages_opened] ),\n"
         "    SUM ( alert_delivery[messages_delivered] ) )", "0.0%"),
        # Sześćdziesiąt procent to próg, poniżej którego alert przestaje być
        # kanałem ostrzegania, a staje się formalnością — takie gminy trzeba
        # obsłużyć obwoźnie, megafonem lub wizytą.
        ("Gminy z dostarczeniem poniżej 60%",
         "COUNTROWS (\n"
         "    FILTER (\n"
         "        SUMMARIZE ( alert_delivery, alert_delivery[gmina_code],\n"
         '            "Skutecznosc", [Skuteczność alertów %] ),\n'
         "        [Skutecznosc] < 0.6\n"
         "    )\n"
         ")", "#,0"),
    ],
    "welfare_check": [
        ("Wizyty kontrolne", "COUNTROWS ( welfare_check )", "#,0"),
        ("Kontakt potwierdzony",
         'CALCULATE ( COUNTROWS ( welfare_check ), welfare_check[result] = "contact_confirmed" )',
         "#,0"),
        ("Ewakuacje",
         'CALCULATE ( COUNTROWS ( welfare_check ), welfare_check[result] = "evacuation" )', "#,0"),
        ("Brak kontaktu",
         'CALCULATE ( COUNTROWS ( welfare_check ), welfare_check[result] = "no_contact" )', "#,0"),
        ("Skuteczność wizyt %",
         "DIVIDE ( [Kontakt potwierdzony], [Wizyty kontrolne] )", "0.0%"),
    ],
    "welfare_check_queue": [
        ("Osoby w kolejce wizyt", "COUNTROWS ( welfare_check_queue )", "#,0"),
        # Poniżej czterech godzin autonomii aparatury nie ma czasu na wizytę
        # planową — to już transport medyczny.
        ("Osoby z autonomią poniżej 4 h",
         "COUNTROWS ( FILTER ( welfare_check_queue,\n"
         "    welfare_check_queue[medical_device_autonomy_hours] < 4 ) )", "#,0"),
        ("Osoby samotne w kolejce",
         "CALCULATE ( COUNTROWS ( welfare_check_queue ),\n"
         "    welfare_check_queue[is_living_alone] = TRUE () )", "#,0"),
        ("Najwyższy priorytet wizyty",
         "MAX ( welfare_check_queue[priority_score] )", "#,0.0"),
    ],
    "welfare_check_routes": [
        ("Zaplanowane wizyty", "COUNTROWS ( welfare_check_routes )", "#,0"),
        ("Zespoły w terenie", "DISTINCTCOUNT ( welfare_check_routes[team_id] )", "#,0"),
        ("Średni czas dojazdu (min)", "AVERAGE ( welfare_check_routes[eta_min] )", "#,0.0"),
    ],
    "heating_point_status": [
        ("Zajętość punktów", "SUM ( heating_point_status[occupancy] )", "#,0"),
        ("Pojemność punktów", "SUM ( heating_point_status[capacity] )", "#,0"),
        ("Wypełnienie punktów %",
         "DIVIDE ( [Zajętość punktów], [Pojemność punktów] )", "0.0%"),
        ("Punkty pełne",
         "COUNTROWS ( FILTER ( heating_point_status,\n"
         "    DIVIDE ( heating_point_status[occupancy], heating_point_status[capacity] ) >= 0.95 ) )",
         "#,0"),
        # Wolne miejsca, a nie zgłoszone potrzeby: flagi needs_* w strumieniu
        # demonstracyjnym pozostają puste, a dyżurny i tak pyta o to samo —
        # ile osób jeszcze przyjmiemy, zanim trzeba otworzyć kolejny punkt.
        ("Wolne miejsca w punktach", "[Pojemność punktów] - [Zajętość punktów]", "#,0"),
    ],
    "dim_care_facility": [
        ("Placówki opiekuńcze", "COUNTROWS ( dim_care_facility )", "#,0"),
        ("Podopieczni w placówkach", "SUM ( dim_care_facility[current_occupancy] )", "#,0"),
        ("Placówki bez zapasu zasilania",
         "CALCULATE ( COUNTROWS ( dim_care_facility ),\n"
         "    FILTER ( dim_care_facility,\n"
         "        dim_care_facility[has_generator] = FALSE ()\n"
         "            || dim_care_facility[generator_autonomy_hours] < 2 ) )", "#,0"),
        ("Zapotrzebowanie mocy placówek (kW)",
         "SUM ( dim_care_facility[power_need_kw] )", "#,0"),
    ],
    "outage_events": [
        ("Awarie zgłoszone", "DISTINCTCOUNT ( outage_events[outage_id] )", "#,0"),
        # outage_events to strumień stanów, nie rejestr awarii: jedna awaria ma
        # kilkadziesiąt wierszy. Sumowanie po wierszach dałoby liczbę odbiorców
        # większą od ludności kraju, więc obie miary biorą ostatni stan awarii.
        # Poza kontekstem czasu obie miary dają zero, bo na końcu horyzontu
        # wszystko jest przywrócone. Zero, a nie pustka: w kafelku odprawy
        # brak wartości czyta się jak brak danych, nie jak brak awarii.
        ("Awarie nieusunięte",
         "COALESCE ( COUNTROWS (\n"
         "    FILTER (\n"
         "        VALUES ( outage_events[outage_id] ),\n"
         "        VAR Ostatni = CALCULATE ( MAX ( outage_events[event_time] ) )\n"
         "        RETURN CALCULATE ( SELECTEDVALUE ( outage_events[status] ),\n"
         "            outage_events[event_time] = Ostatni ) <> \"restored\"\n"
         "    )\n"
         "), 0 )", "#,0"),
        ("Odbiorcy w czynnych awariach",
         "COALESCE ( SUMX (\n"
         "    VALUES ( outage_events[outage_id] ),\n"
         "    VAR Ostatni = CALCULATE ( MAX ( outage_events[event_time] ) )\n"
         "    VAR Stan = CALCULATE ( SELECTEDVALUE ( outage_events[status] ),\n"
         "        outage_events[event_time] = Ostatni )\n"
         "    VAR Odbiorcy = CALCULATE ( SELECTEDVALUE ( outage_events[customers_without_power] ),\n"
         "        outage_events[event_time] = Ostatni )\n"
         "    RETURN IF ( Stan <> \"restored\", Odbiorcy )\n"
         "), 0 )", "#,0"),
        # Szczyt jest tym, co pada w meldunku: ilu odbiorców było bez prądu
        # w najgorszej godzinie. Suma po strumieniu nie odpowiada na to pytanie.
        ("Szczyt odbiorców bez zasilania",
         "MAXX ( VALUES ( outage_events[event_time] ),\n"
         "    CALCULATE ( SUM ( outage_events[customers_without_power] ) ) )", "#,0"),
        ("Najgłębszy etap kaskady", "MAX ( outage_events[cascade_stage] )", "#,0"),
    ],
    "telecom_coverage": [
        ("Pokrycie telekomunikacyjne %", "AVERAGE ( telecom_coverage[coverage_pct] )", "0.0%"),
        ("Stacje na akumulatorach", "SUM ( telecom_coverage[bts_on_battery] )", "#,0"),
        ("Zapas akumulatorów (h)",
         "MIN ( telecom_coverage[battery_hours_remaining] )", "#,0.0"),
    ],
    "emergency_calls": [
        ("Zgłoszenia alarmowe", "COUNTROWS ( emergency_calls )", "#,0"),
        ("Zgłoszenia P1",
         'CALCULATE ( COUNTROWS ( emergency_calls ), emergency_calls[priority] = "P1" )', "#,0"),
    ],
    "whatif_extended_outage": [
        # Wariant „awaria trwa dłużej" pokazuje, ile gmin przekroczy próg
        # krytyczny, jeśli nic nie zrobimy — to argument za wcześniejszą decyzją.
        ("Gminy krytyczne w wariancie",
         "CALCULATE ( DISTINCTCOUNT ( whatif_extended_outage[gmina_code] ),\n"
         "    whatif_extended_outage[whatif_izz] >= 75 )", "#,0"),
        ("Przyrost gmin krytycznych",
         "[Gminy krytyczne w wariancie] - [Gminy krytyczne]", "#,0"),
        ("IZŻ w wariancie", "AVERAGE ( whatif_extended_outage[whatif_izz] )", "#,0.0"),
    ],
    "fact_population_vulnerability": [
        ("Populacja objęta analizą", "SUM ( fact_population_vulnerability[population] )", "#,0"),
        ("Szacowana populacja wrażliwa",
         "SUM ( fact_population_vulnerability[vulnerable_population_est] )", "#,0"),
        ("Udział populacji wrażliwej %",
         "DIVIDE ( [Szacowana populacja wrażliwa], [Populacja objęta analizą] )", "0.0%"),
    ],
    "fact_priority_persons": [
        ("Osoby priorytetowe", "DISTINCTCOUNT ( fact_priority_persons[person_token] )", "#,0"),
        ("Kontakt priorytetowy potwierdzony %",
         "DIVIDE ( [Kontakt potwierdzony], [Osoby priorytetowe] )", "0.0%"),
    ],
    "dim_generator_stock": [
        ("Agregaty w magazynach", "COUNTROWS ( dim_generator_stock )", "#,0"),
        ("Agregaty dostępne",
         'CALCULATE ( COUNTROWS ( dim_generator_stock ), dim_generator_stock[status] = "available" )',
         "#,0"),
        ("Moc dostępna (kW)",
         'CALCULATE ( SUM ( dim_generator_stock[power_kw] ),\n'
         '    dim_generator_stock[status] = "available" )', "#,0"),
    ],
    "generator_dispatch": [
        ("Wydania agregatów", "COUNTROWS ( generator_dispatch )", "#,0"),
        ("Moc wydana (kW)", "SUM ( generator_dispatch[power_kw] )", "#,0"),
    ],
    "iwl_by_gmina": [
        ("Średni IWL", "AVERAGE ( iwl_by_gmina[iwl_score] )", "#,0.0"),
        ("Maksymalny IWL", "MAX ( iwl_by_gmina[iwl_score] )", "#,0.0"),
    ],
    "weather_readings": [
        ("Najniższa odczuwalna (°C)", "MIN ( weather_readings[feels_like_c] )", "#,0.0"),
        ("Maksymalny wiatr (km/h)", "MAX ( weather_readings[wind_kmh] )", "#,0.0"),
    ],
    "critical_crossing_times": [
        ("Gminy z przekroczeniem progu", "COUNTROWS ( critical_crossing_times )", "#,0"),
    ],
    "dim_gmina": [
        ("Gminy w rejestrze", "COUNTROWS ( dim_gmina )", "#,0"),
        ("Ludność rejestru", "SUM ( dim_gmina[population] )", "#,0"),
    ],
    "dim_heating_point": [
        ("Punkty grzewcze w rejestrze", "COUNTROWS ( dim_heating_point )", "#,0"),
        ("Punkty z własnym zasilaniem",
         "CALCULATE ( COUNTROWS ( dim_heating_point ),\n"
         "    dim_heating_point[has_generator] = TRUE () )", "#,0"),
    ],
}

# Pokrycie i jego przyrost to dwie miary, które muszą stać obok siebie: sama
# wartość nic nie mówi, dopóki nie widać, ile daje ponad podział „po równo".
MEASURES["selected_heating_points"].append((
    "Pokrycie punktami grzewczymi %",
    "DIVIDE ( SUM ( selected_heating_points[covered_vulnerable_est] ),\n"
    "    SUM ( dynamic_risk_latest[vulnerable_without_power] ) )", "0.0%"))
MEASURES["selected_heating_points"].append((
    "Poprawa pokrycia p.p.",
    "( [Pokrycie punktami grzewczymi %] - 0.131 ) * 100", "#,0.0"))

RELATIONSHIPS = [
    ("dim_voivodeship", "voivodeship_code", "dim_powiat", "voivodeship_code"),
    ("dim_powiat", "powiat_code", "dim_gmina", "powiat_code"),
    ("dim_gmina", "gmina_code", "fact_population_vulnerability", "gmina_code"),
    ("dim_gmina", "gmina_code", "fact_priority_persons", "gmina_code"),
    ("dim_gmina", "gmina_code", "dynamic_risk_latest", "gmina_code"),
    ("dim_gmina", "gmina_code", "critical_gminas_latest", "gmina_code"),
    ("dim_gmina", "gmina_code", "critical_crossing_times", "gmina_code"),
    ("dim_gmina", "gmina_code", "whatif_extended_outage", "gmina_code"),
    ("dim_gmina", "gmina_code", "iwl_by_gmina", "gmina_code"),
    ("dim_gmina", "gmina_code", "selected_heating_points", "gmina_code"),
    ("dim_gmina", "gmina_code", "welfare_check_queue", "gmina_code"),
    ("dim_gmina", "gmina_code", "welfare_check_routes", "gmina_code"),
    ("dim_gmina", "gmina_code", "welfare_check", "gmina_code"),
    ("dim_gmina", "gmina_code", "alert_delivery", "gmina_code"),
    ("dim_gmina", "gmina_code", "emergency_calls", "gmina_code"),
    ("dim_gmina", "gmina_code", "telecom_coverage", "gmina_code"),
    ("dim_gmina", "gmina_code", "outage_events", "gmina_code"),
    ("dim_gmina", "gmina_code", "dim_care_facility", "gmina_code"),
    ("dim_gmina", "gmina_code", "dim_heating_point", "gmina_code"),
    ("dim_gmina", "gmina_code", "generator_dispatch", "gmina_code"),
    ("dim_powiat", "powiat_code", "weather_readings", "powiat_code"),
    ("dim_generator_stock", "generator_id", "generator_dispatch", "generator_id"),
    # Punkt grzewczy filtruje status; gmina dociera do statusu przez rejestr punktów,
    # więc druga noga (gmina -> status) byłaby drugą ścieżką i musi zostać nieaktywna.
    ("dim_heating_point", "heating_point_id", "heating_point_status", "heating_point_id"),
    ("dim_heating_point", "heating_point_id", "selected_heating_points", "heating_point_id", False),
    ("dim_gmina", "gmina_code", "heating_point_status", "gmina_code", False),
]

# Tabele źródłowe wag i pełny wynik IWL zasilają notatniki i aplikację,
# a nie raport decydenta.
HIDDEN_TABLES = {"dim_vulnerability_factors"}
