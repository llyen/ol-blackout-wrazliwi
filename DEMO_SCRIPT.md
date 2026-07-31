# Demo script — Tarcza Zimowa, 15–20 minut

## Cel pokazu

Pokaz ma przekonać decydenta, że w długotrwałym blackoucie zimowym najważniejsza nie jest sama mapa awarii, lecz odpowiedź na pytanie: **kto jest najbardziej zagrożony, gdzie się znajduje i jak szybko administracja może dowieźć ciepło, zasilanie, schronienie i kontakt**. Scenariusz używa osi „MRÓZ STYCZEŃ” oraz zagrożeń KPZK `Z19 Silny mróz/intensywne opady śniegu` i `Z07 Zakłócenie w systemie energetycznym`, z wtórnymi skutkami `Z12 Telekomunikacja` i `Z01 Zdrowie`. Narracja prowadzi od prognozy, przez awarię, do decyzji RCB/RZZK/MSWiA/MZ/MRPiPS oraz działań gminy i OSP.

Wszystkie liczby są policzone lokalnie z `datasets\derived\`:

- Rekordy: 2477 gmin, 380 powiatów, 900 placówek opieki, 500 punktów grzewczych, 420 agregatów, 1250 fikcyjnych osób priorytetowych.
- Strumienie: pogoda 201020, awarie 6650, łączność 522647, zgłoszenia 112 5285, status punktów 330, wydania agregatów 260, wizyty 202, alerty 7431.
- IWL: średnia 63.03, P90 79.83, top gmina 2817005.
- IZŻ: gminy krytyczne 14, osoby wrażliwe bez zasilania 317,719, maks. czas bez prądu 59.3 h.
- Optymalizacja: wybrano 80 punktów, przydzielono 29 agregatów; pokrycie 36.7% vs 13.1% „po równo” (+23.6 p.p.).
- Wizyty: kolejka 500 osób, pierwsza zmiana obsługuje 147 wizyt, zespoły 16; w Top100 jest 37 pacjentów tlenoterapii i 11 dializowanych.
- What-if: gminy krytyczne rosną z 14 do 104 (+90).

## Obsada ról

- **Prezenter** — prowadzi historię, przełącza ekrany, pilnuje czasu i tłumaczy, dlaczego kolejne liczby mają znaczenie dla decyzji.
- **Dyrektor RCB** — reprezentuje poziom krajowy; pyta o priorytety, eskalację do RZZK, SPO-3 i potencjalne przesłanki SPO-5.
- **Wojewoda podlaski** — odpowiada za koordynację w województwie; akceptuje plan punktów grzewczych i agregatów.
- **Wójt gminy** — pokazuje lokalną perspektywę: remizy, szkoły, świetlice, mieszkańcy bez ogrzewania i łączności.
- **Druh OSP** — odbiera listę wizyt kontrolnych i pokazuje pracę terenową także przy braku zasięgu.
- **Koordynator medyczny** — interpretuje ryzyko dla osób z tlenoterapią, dializowanych i placówek opieki.
- **Minister** — zadaje pytania decyzyjne: czy wiemy, komu grozi utrata życia, czy mamy zasoby, czy algorytm zastępuje człowieka.

## Checklista przed demo

1. Otwórz repo `C:\repos\OchronaLudnosci\ol-blackout-wrazliwi`.
2. Sprawdź, że istnieją `datasets\derived\dynamic_risk_latest.csv`, `selected_heating_points.csv`, `welfare_check_queue.csv` i `whatif_summary.json`.
3. W razie potrzeby uruchom: `python generate_datasets.py`, notebooki `02`–`06`, potem `python update_results.py`.
4. Uruchom `python simulate_realtime.py --dry-run` i zapamiętaj, że wybrano 735602 zdarzeń z 4 głównych strumieni RT.
5. W Fabric odśwież Lakehouse `WinterShield_LH`, Eventhouse `WinterShield_KQL` i model semantyczny.
6. Otwórz Power BI na stronie **Mapa kraju IZŻ**.
7. Otwórz Fabric App na ekranie **Decydent krajowy**.
8. Przygotuj zakładkę **Data Agent** z pytaniem „Które gminy są dziś w stanie krytycznym i dlaczego?”.
9. Przygotuj zakładkę **Activator** z regułą `CareFacility_Autonomy_Low`.
10. Przygotuj plan B: lokalny `DEMO_SCRIPT.md`, `datasets\derived\*.csv` i `report\REPORT_SPEC.md`.


## Akt I. D-2 prognoza mrozu i oblodzenia (0:00–4:00)

**Kwestia prezentera:** „Proszę zauważyć, że nie zaczynamy od technologii, tylko od decyzji operacyjnej. W mrozie i blackoucie czas liczy się inaczej: po kilku godzinach padają baterie BTS, po kilkunastu godzinach kończy się autonomia urządzeń medycznych, a po dobie rośnie ryzyko wychłodzenia. Ten ekran odpowiada na pytanie, gdzie najpierw wysłać ludzi i zasoby.”

**Kwestia roli decyzyjnej:** „Nie potrzebuję kolejnego arkusza z listą gmin. Potrzebuję wiedzieć, które miejsce przekroczyło próg krytyczny, dlaczego model tak uważa i jaką decyzję mogę podjąć w ciągu najbliższych 15 minut.”

**Co kliknąć:** otwórz **Ekran 1 — Decydent krajowy**, wybierz filtr `time_axis = D-2`, kafel `Weather severity`, warstwa `icing_index`. Jeżeli pokazujesz Power BI, użyj slicera województwa i drill-through do gminy. Jeżeli pokazujesz Fabric App, użyj przycisku akcji i pokaż write-back albo alert.

**Co widz zobaczy:** prognozę mrozu, wiatr, śnieg i wzrost ryzyka Z19 jeszcze przed awarią. Warto zatrzymać się na tooltipie, bo pokazuje jednocześnie IWL, temperaturę odczuwalną, godziny bez prądu, łączność i rekomendację operacyjną.

**Liczby do wypowiedzenia:** „W tym kroku padają konkretne wartości: prognozę mrozu, wiatr, śnieg i wzrost ryzyka Z19 jeszcze przed awarią. To nie są liczby wpisane do slajdu — pochodzą z wyników notebooków i strumieni wygenerowanych z seed=42.”

**Puenta:** „Ten krok zamienia dane w zadanie: kto ma zareagować, jaki zasób wysłać, jak sprawdzić efekt i kiedy eskalować.”

## Akt II. D0 kaskadowa awaria sieci (2:00–6:00)

**Kwestia prezentera:** „Proszę zauważyć, że nie zaczynamy od technologii, tylko od decyzji operacyjnej. W mrozie i blackoucie czas liczy się inaczej: po kilku godzinach padają baterie BTS, po kilkunastu godzinach kończy się autonomia urządzeń medycznych, a po dobie rośnie ryzyko wychłodzenia. Ten ekran odpowiada na pytanie, gdzie najpierw wysłać ludzi i zasoby.”

**Kwestia roli decyzyjnej:** „Nie potrzebuję kolejnego arkusza z listą gmin. Potrzebuję wiedzieć, które miejsce przekroczyło próg krytyczny, dlaczego model tak uważa i jaką decyzję mogę podjąć w ciągu najbliższych 15 minut.”

**Co kliknąć:** otwórz **Ekran 1 — Decydent krajowy**, wybierz kafelek `Outage cascade`, filtr województw: podlaskie, warmińsko-mazurskie, mazowieckie, lubelskie. Jeżeli pokazujesz Power BI, użyj slicera województwa i drill-through do gminy. Jeżeli pokazujesz Fabric App, użyj przycisku akcji i pokaż write-back albo alert.

**Co widz zobaczy:** kaskadę na mapie i pierwsze gminy z utratą zasilania. Warto zatrzymać się na tooltipie, bo pokazuje jednocześnie IWL, temperaturę odczuwalną, godziny bez prądu, łączność i rekomendację operacyjną.

**Liczby do wypowiedzenia:** „W tym kroku padają konkretne wartości: kaskadę na mapie i pierwsze gminy z utratą zasilania. To nie są liczby wpisane do slajdu — pochodzą z wyników notebooków i strumieni wygenerowanych z seed=42.”

**Puenta:** „Ten krok zamienia dane w zadanie: kto ma zareagować, jaki zasób wysłać, jak sprawdzić efekt i kiedy eskalować.”

## Akt III. Mapa gmin krytycznych i ranking IZŻ (4:00–8:00)

**Kwestia prezentera:** „Proszę zauważyć, że nie zaczynamy od technologii, tylko od decyzji operacyjnej. W mrozie i blackoucie czas liczy się inaczej: po kilku godzinach padają baterie BTS, po kilkunastu godzinach kończy się autonomia urządzeń medycznych, a po dobie rośnie ryzyko wychłodzenia. Ten ekran odpowiada na pytanie, gdzie najpierw wysłać ludzi i zasoby.”

**Kwestia roli decyzyjnej:** „Nie potrzebuję kolejnego arkusza z listą gmin. Potrzebuję wiedzieć, które miejsce przekroczyło próg krytyczny, dlaczego model tak uważa i jaką decyzję mogę podjąć w ciągu najbliższych 15 minut.”

**Co kliknąć:** otwórz **Mapa kraju IZŻ**, wybierz kafle `Critical gminas`, `Vulnerable without power`, tabela `Ranking IZŻ`. Jeżeli pokazujesz Power BI, użyj slicera województwa i drill-through do gminy. Jeżeli pokazujesz Fabric App, użyj przycisku akcji i pokaż write-back albo alert.

**Co widz zobaczy:** 14 gmin krytycznych i 317,719 osób wrażliwych bez zasilania. Warto zatrzymać się na tooltipie, bo pokazuje jednocześnie IWL, temperaturę odczuwalną, godziny bez prądu, łączność i rekomendację operacyjną.

**Liczby do wypowiedzenia:** „W tym kroku padają konkretne wartości: 14 gmin krytycznych i 317,719 osób wrażliwych bez zasilania. To nie są liczby wpisane do slajdu — pochodzą z wyników notebooków i strumieni wygenerowanych z seed=42.”

**Puenta:** „Ten krok zamienia dane w zadanie: kto ma zareagować, jaki zasób wysłać, jak sprawdzić efekt i kiedy eskalować.”

## Akt IV. Plan agregatów i punktów grzewczych (6:00–10:00)

**Kwestia prezentera:** „Proszę zauważyć, że nie zaczynamy od technologii, tylko od decyzji operacyjnej. W mrozie i blackoucie czas liczy się inaczej: po kilku godzinach padają baterie BTS, po kilkunastu godzinach kończy się autonomia urządzeń medycznych, a po dobie rośnie ryzyko wychłodzenia. Ten ekran odpowiada na pytanie, gdzie najpierw wysłać ludzi i zasoby.”

**Kwestia roli decyzyjnej:** „Nie potrzebuję kolejnego arkusza z listą gmin. Potrzebuję wiedzieć, które miejsce przekroczyło próg krytyczny, dlaczego model tak uważa i jaką decyzję mogę podjąć w ciągu najbliższych 15 minut.”

**Co kliknąć:** otwórz **Ekran 2 — Wojewoda**, wybierz przycisk `Generate optimized plan`, filtr `show selected only`. Jeżeli pokazujesz Power BI, użyj slicera województwa i drill-through do gminy. Jeżeli pokazujesz Fabric App, użyj przycisku akcji i pokaż write-back albo alert.

**Co widz zobaczy:** 80 punktów, 29 agregatów, pokrycie 36.7% vs 13.1%. Warto zatrzymać się na tooltipie, bo pokazuje jednocześnie IWL, temperaturę odczuwalną, godziny bez prądu, łączność i rekomendację operacyjną.

**Liczby do wypowiedzenia:** „W tym kroku padają konkretne wartości: 80 punktów, 29 agregatów, pokrycie 36.7% vs 13.1%. To nie są liczby wpisane do slajdu — pochodzą z wyników notebooków i strumieni wygenerowanych z seed=42.”

**Puenta:** „Ten krok zamienia dane w zadanie: kto ma zareagować, jaki zasób wysłać, jak sprawdzić efekt i kiedy eskalować.”

## Akt V. Wizyty kontrolne OSP (8:00–12:00)

**Kwestia prezentera:** „Proszę zauważyć, że nie zaczynamy od technologii, tylko od decyzji operacyjnej. W mrozie i blackoucie czas liczy się inaczej: po kilku godzinach padają baterie BTS, po kilkunastu godzinach kończy się autonomia urządzeń medycznych, a po dobie rośnie ryzyko wychłodzenia. Ten ekran odpowiada na pytanie, gdzie najpierw wysłać ludzi i zasoby.”

**Kwestia roli decyzyjnej:** „Nie potrzebuję kolejnego arkusza z listą gmin. Potrzebuję wiedzieć, które miejsce przekroczyło próg krytyczny, dlaczego model tak uważa i jaką decyzję mogę podjąć w ciągu najbliższych 15 minut.”

**Co kliknąć:** otwórz **Ekran 3 — Gmina/OSP**, wybierz zakładka `Welfare check queue`, sortowanie po `priority_score`, przycisk `Open route`. Jeżeli pokazujesz Power BI, użyj slicera województwa i drill-through do gminy. Jeżeli pokazujesz Fabric App, użyj przycisku akcji i pokaż write-back albo alert.

**Co widz zobaczy:** kolejkę 500 osób i 147 wizyt w pierwszej zmianie. Warto zatrzymać się na tooltipie, bo pokazuje jednocześnie IWL, temperaturę odczuwalną, godziny bez prądu, łączność i rekomendację operacyjną.

**Liczby do wypowiedzenia:** „W tym kroku padają konkretne wartości: kolejkę 500 osób i 147 wizyt w pierwszej zmianie. To nie są liczby wpisane do slajdu — pochodzą z wyników notebooków i strumieni wygenerowanych z seed=42.”

**Puenta:** „Ten krok zamienia dane w zadanie: kto ma zareagować, jaki zasób wysłać, jak sprawdzić efekt i kiedy eskalować.”

## Akt VI. Alert o placówce z autonomią 90 minut (10:00–14:00)

**Kwestia prezentera:** „Proszę zauważyć, że nie zaczynamy od technologii, tylko od decyzji operacyjnej. W mrozie i blackoucie czas liczy się inaczej: po kilku godzinach padają baterie BTS, po kilkunastu godzinach kończy się autonomia urządzeń medycznych, a po dobie rośnie ryzyko wychłodzenia. Ten ekran odpowiada na pytanie, gdzie najpierw wysłać ludzi i zasoby.”

**Kwestia roli decyzyjnej:** „Nie potrzebuję kolejnego arkusza z listą gmin. Potrzebuję wiedzieć, które miejsce przekroczyło próg krytyczny, dlaczego model tak uważa i jaką decyzję mogę podjąć w ciągu najbliższych 15 minut.”

**Co kliknąć:** otwórz **Data Activator / Alert center**, wybierz reguła `CareFacility_Autonomy_Low`, przycisk `Assign generator`. Jeżeli pokazujesz Power BI, użyj slicera województwa i drill-through do gminy. Jeżeli pokazujesz Fabric App, użyj przycisku akcji i pokaż write-back albo alert.

**Co widz zobaczy:** alert, odbiorcę, SLA i rekomendację agregat/ewakuacja. Warto zatrzymać się na tooltipie, bo pokazuje jednocześnie IWL, temperaturę odczuwalną, godziny bez prądu, łączność i rekomendację operacyjną.

**Liczby do wypowiedzenia:** „W tym kroku padają konkretne wartości: alert, odbiorcę, SLA i rekomendację agregat/ewakuacja. To nie są liczby wpisane do slajdu — pochodzą z wyników notebooków i strumieni wygenerowanych z seed=42.”

**Puenta:** „Ten krok zamienia dane w zadanie: kto ma zareagować, jaki zasób wysłać, jak sprawdzić efekt i kiedy eskalować.”

## Akt VII. Komunikat do ludności SPO-3 (12:00–16:00)

**Kwestia prezentera:** „Proszę zauważyć, że nie zaczynamy od technologii, tylko od decyzji operacyjnej. W mrozie i blackoucie czas liczy się inaczej: po kilku godzinach padają baterie BTS, po kilkunastu godzinach kończy się autonomia urządzeń medycznych, a po dobie rośnie ryzyko wychłodzenia. Ten ekran odpowiada na pytanie, gdzie najpierw wysłać ludzi i zasoby.”

**Kwestia roli decyzyjnej:** „Nie potrzebuję kolejnego arkusza z listą gmin. Potrzebuję wiedzieć, które miejsce przekroczyło próg krytyczny, dlaczego model tak uważa i jaką decyzję mogę podjąć w ciągu najbliższych 15 minut.”

**Co kliknąć:** otwórz **Ekran 5 — Komunikacja SPO-3**, wybierz wybór gmin krytycznych, kanały `RSO`, `SMS`, `local_radio`, kafel `Delivery rate`. Jeżeli pokazujesz Power BI, użyj slicera województwa i drill-through do gminy. Jeżeli pokazujesz Fabric App, użyj przycisku akcji i pokaż write-back albo alert.

**Co widz zobaczy:** 7431 rekordów wysyłki i pomiar dotarcia. Warto zatrzymać się na tooltipie, bo pokazuje jednocześnie IWL, temperaturę odczuwalną, godziny bez prądu, łączność i rekomendację operacyjną.

**Liczby do wypowiedzenia:** „W tym kroku padają konkretne wartości: 7431 rekordów wysyłki i pomiar dotarcia. To nie są liczby wpisane do slajdu — pochodzą z wyników notebooków i strumieni wygenerowanych z seed=42.”

**Puenta:** „Ten krok zamienia dane w zadanie: kto ma zareagować, jaki zasób wysłać, jak sprawdzić efekt i kiedy eskalować.”

## Akt VIII. What-if: awaria +12h (14:00–18:00)

**Kwestia prezentera:** „Proszę zauważyć, że nie zaczynamy od technologii, tylko od decyzji operacyjnej. W mrozie i blackoucie czas liczy się inaczej: po kilku godzinach padają baterie BTS, po kilkunastu godzinach kończy się autonomia urządzeń medycznych, a po dobie rośnie ryzyko wychłodzenia. Ten ekran odpowiada na pytanie, gdzie najpierw wysłać ludzi i zasoby.”

**Kwestia roli decyzyjnej:** „Nie potrzebuję kolejnego arkusza z listą gmin. Potrzebuję wiedzieć, które miejsce przekroczyło próg krytyczny, dlaczego model tak uważa i jaką decyzję mogę podjąć w ciągu najbliższych 15 minut.”

**Co kliknąć:** otwórz **Strona What-if**, wybierz suwaki `outage +12h`, `temperature -5C`, `generators -30%`. Jeżeli pokazujesz Power BI, użyj slicera województwa i drill-through do gminy. Jeżeli pokazujesz Fabric App, użyj przycisku akcji i pokaż write-back albo alert.

**Co widz zobaczy:** wzrost z 14 do 104 gmin krytycznych. Warto zatrzymać się na tooltipie, bo pokazuje jednocześnie IWL, temperaturę odczuwalną, godziny bez prądu, łączność i rekomendację operacyjną.

**Liczby do wypowiedzenia:** „W tym kroku padają konkretne wartości: wzrost z 14 do 104 gmin krytycznych. To nie są liczby wpisane do slajdu — pochodzą z wyników notebooków i strumieni wygenerowanych z seed=42.”

**Puenta:** „Ten krok zamienia dane w zadanie: kto ma zareagować, jaki zasób wysłać, jak sprawdzić efekt i kiedy eskalować.”

## Wow moments

1. **14 gmin krytycznych zamiast czerwonej mapy wszystkiego.** Decydent dostaje krótką listę miejsc wymagających natychmiastowej reakcji, a nie wizualny alarm bez priorytetów. Działa, bo redukuje chaos informacyjny w pierwszej odprawie.
2. **317 719 osób wrażliwych bez zasilania jako liczba decyzyjna.** To przenosi rozmowę z „ile odbiorców nie ma prądu” na „ile osób może nie przetrwać bez pomocy”. Działa, bo dotyka celu ochrony ludności.
3. **Optymalizacja 36,7% vs 13,1% (+23,6 p.p.).** Wojewoda widzi, że model nie tylko raportuje problem, ale poprawia wykorzystanie rzadkich agregatów i punktów grzewczych. Działa, bo pokazuje wymierną przewagę nad rozdziałem „po równo”.
4. **OSP dostaje trasę i listę wizyt.** Widz rozumie, że analityka schodzi do poziomu działania w terenie. Działa, bo zamyka lukę między centrum krajowym a drzwiami mieszkańca.
5. **What-if 14 → 104 gminy krytyczne.** Minister widzi konsekwencję opóźnienia o 12 godzin. Działa, bo pokazuje koszt braku decyzji, a nie abstrakcyjny scenariusz.

## Wartość biznesowa

- **Życie ludzkie:** priorytetem są osoby starsze samotne, pacjenci tlenoterapii, dializowani i placówki opieki; model wskazuje, gdzie brak zasilania i mróz tworzą zagrożenie życia.
- **Czas dotarcia pomocy:** kolejka wizyt i trasy OSP skracają czas od wykrycia ryzyka do kontaktu z osobą. Pierwsza zmiana obejmuje 147 wizyt, co daje mierzalny plan pracy.
- **Agregaty i ciepło:** ograniczona liczba agregatów nie jest dzielona politycznie ani „po równo”, tylko według pokrycia osób wrażliwych, mocy i dostępności punktów.
- **Zgodność z ustawą o ZK i ochroną ludności:** poziomy reagowania są czytelne: gmina realizuje wizyty i punkty grzewcze, wojewoda koordynuje zasoby, RCB/RZZK widzi obraz krajowy i przesłanki SPO-3/SPO-5.
- **Rozliczalność:** decyzje write-back, alerty, statusy punktów i potwierdzenia wizyt tworzą ślad audytowy po zdarzeniu.

## Plan B

- **Awaria aplikacji:** przejdź do Power BI i lokalnych plików `datasets\derived\critical_gminas_latest.csv`, `selected_heating_points.csv`, `welfare_check_queue.csv`.
- **Brak sieci u OSP:** użyj trybu offline aplikacji — ostatnio zsynchronizowana kolejka i mapa są dostępne lokalnie, a wyniki wizyt zapisują się w kolejce wysyłki.
- **Dane się nie odświeżają:** pokaż timestamp `snapshot_time` w `dynamic_risk_summary.json` i uruchom lokalnie notebook `03_dynamic_risk.py`.
- **Eventstream nie działa:** użyj `simulate_realtime.py --dry-run`; dowodzi parsowania i kolejności zdarzeń bez poświadczeń.
- **Data Agent nie odpowiada:** użyj zapytań z `kql\03_dashboard_queries.kql` i `04_risk_correlation.kql`.
- **Projektor/Power BI zawodzi:** narrację można przeprowadzić z tego dokumentu i plików CSV, bo wszystkie liczby są zapisane w `datasets\derived`.

## Najczęstsze pytania decydenta i odpowiedzi

1. **Skąd dane o pacjentach tlenoterapii i dializowanych?** W demo są fikcyjne. W produkcji źródłem byłyby prawnie umocowane rejestry ochrony zdrowia i świadczeniodawców, przekazywane w minimalnym zakresie niezbędnym do ochrony życia.
2. **Kto ma dostęp do danych wrażliwych?** Poziom krajowy widzi agregaty. Gmina/OSP widzi tylko osoby przypisane do wizyty, a koordynator medyczny kategorie i autonomię urządzeń. Dostęp jest kontrolowany przez RLS, role Entra ID, etykiety Purview i audyt.
3. **Jaka jest podstawa prawna?** Dla realnego wdrożenia trzeba oprzeć się na RODO art. 6 i 9, w tym żywotnych interesach osoby oraz zadaniach realizowanych w interesie publicznym, a także na ustawie o zarządzaniu kryzysowym i przepisach ochrony ludności.
4. **Czy algorytm zastępuje człowieka?** Nie. Algorytm układa ranking i rekomendacje, ale decyzję zatwierdza wojewoda, wójt, koordynator medyczny albo RCB/RZZK. Human-in-the-loop jest zasadą.
5. **Czy można zintegrować OSD/PSE?** Tak. Eventstream/Eventhouse przyjmie zdarzenia awarii z operatorów, a Lakehouse przechowa słowniki zasobów i mapowanie gmin.
6. **Czy można zintegrować NFZ i opiekę społeczną?** Tak, ale wyłącznie po uzgodnieniu podstaw prawnych, zakresu danych, retencji i RLS. Preferowany jest model agregat + lista priorytetowa tylko dla uprawnionych.
7. **Ile trwa wdrożenie?** MVP dla jednego województwa i kilku strumieni można planować etapami; najdłuższe są uzgodnienia danych i bezpieczeństwa, nie samo zbudowanie dashboardu.
8. **Jaki koszt?** Koszt zależy od capacity Fabric, liczby użytkowników i wolumenów. Demo pokazuje, że jedna platforma obsługuje strumienie, Lakehouse, KQL, raport, aplikację, agentów i alerty.
9. **Co jeśli system sam padnie w blackoucie?** W realnym wdrożeniu musi działać w chmurze z redundancją, mieć procedury offline, zapasowe łącza, eksport paczek dla gmin i papierowy tryb awaryjny.
10. **Czy obywatel wie, że jest w rejestrze priorytetowym?** W produkcji powinien istnieć jasny obowiązek informacyjny albo właściwie udokumentowany wyjątek kryzysowy, a po zdarzeniu informacja i prawo kontroli zgodnie z prawem.
11. **Czy model może dyskryminować gminy wiejskie?** Ryzyko istnieje, dlatego ranking ma wyjaśnialne czynniki, a decyzję zatwierdza człowiek. Celem jest wyrównanie szans dotarcia pomocy, nie karanie za oddalenie.
12. **Co jest dowodem działania demo?** Pliki `datasets\derived\*.json` i `*.csv`, wyniki w README oraz możliwość ponownego uruchomienia skryptów z seed=42.
