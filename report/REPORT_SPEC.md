# Report spec — Power BI

## Strona 1. Mapa kraju IZŻ

**Cel:** krajowy obraz zagrożenia życia. **Odbiorca:** RCB, minister, RZZK. **Wizualizacje:** mapa kształtów gmin (`gmina_code`, `izz_score`, `life_threat_level`), KPI `Critical Gminas`, KPI `Vulnerable Without Power`, wykres słupkowy top województw, tooltip z IWL, godzinami bez prądu, łącznością i temperaturą. **Filtry:** czas snapshotu, województwo, poziom ryzyka. **Interakcje:** kliknięcie gminy filtruje ranking i drill-through do szczegółu.

## Strona 2. Ranking gmin krytycznych

**Cel:** wskazać kolejność decyzji. **Odbiorca:** dyrektor RCB, wojewoda. **Wizualizacje:** tabela Top50 z `izz_score`, `iwl_score`, `vulnerable_without_power`, `hours_without_power`, `coverage_pct`; waterfall czynników IZŻ; karta pierwszego przekroczenia progu z `critical_crossing_times`. **Filtry:** województwo, powiat, tylko critical/high. **Drill-through:** do gminy i punktów grzewczych.

## Strona 3. Osoby priorytetowe

**Cel:** kontrolować pracę OSP i medyczne priorytety. **Odbiorca:** gmina, koordynator medyczny. **Wizualizacje:** tabela kolejki, histogram kategorii, KPI top100 tlenoterapia/dializy, mapa tras, status wizyt. **Filtry:** gmina, kategoria, autonomia urządzenia, wynik wizyty. **Bezpieczeństwo:** strona ukryta dla ról krajowych bez uprawnienia indywidualnego; eksport wyłączony.

## Strona 4. Punkty grzewcze i agregaty

**Cel:** ocenić pokrycie potrzeb. **Odbiorca:** wojewoda, logistyka. **Wizualizacje:** mapa punktów, tabela `selected_heating_points`, KPI `Heating Point Coverage %`, KPI `Generators Assigned`, wykres pokrycia 36,7% vs 13,1%, lista braków mocy. **Filtry:** województwo, status punktu, wymaga agregatu. **Interakcje:** kliknięcie punktu pokazuje gminy pokryte i zapotrzebowanie.

## Strona 5. Skuteczność ostrzegania SPO-3

**Cel:** sprawdzić, czy komunikat dotarł. **Odbiorca:** RCB, wojewoda, rzecznik. **Wizualizacje:** matrix kanał × województwo, KPI `Alert Delivery %`, mapa gmin z dostarczeniem <60%, trend wysyłek, tabela retry. **Filtry:** kanał `RSO/SMS/local_radio`, gmina, czas. **Drill-through:** do gmin bez łączności.

## Strona 6. What-if

**Cel:** pokazać konsekwencje opóźnienia. **Odbiorca:** minister, RZZK. **Wizualizacje:** slicery awaria +12h, temperatura -5°C, agregaty -30%; KPI baseline 14 i what-if 104; mapa różnicy; tabela nowych gmin krytycznych. **Interakcje:** bookmark „Plan B” i „Eskalacja SPO-5”. **Układ:** po lewej założenia, w centrum mapa, po prawej rekomendacje.

## Układ i standardy

Wszystkie strony mają pasek nagłówka z datą snapshotu, disclaimerem „dane syntetyczne” i filtrem województwa. Kolory: monitoring szary/niebieski, elevated żółty, high pomarańczowy, critical czerwony/brązowy. Tooltips mają zawsze odpowiedź „dlaczego”: IWL, temperatura, prąd, łączność, dojazd.

## Drill-through: karta gminy

Każda strona powinna prowadzić do wspólnej karty gminy. Karta pokazuje: nazwa, województwo, IWL, IZŻ, liczba osób wrażliwych bez zasilania, godziny bez prądu, średnie pokrycie telco, liczba zgłoszeń P1, najbliższe punkty grzewcze, status kampanii SPO-3 i rekomendowane działania. Karta nie pokazuje listy osób, chyba że rola ma uprawnienie operacyjne.

## Miary i formaty

KPI krajowe mają format całkowity z separatorem tysięcy. Procenty mają jedno miejsce po przecinku. IZŻ i IWL mają zakres 0–100 i jedno miejsce po przecinku. Daty pokazuj w czasie lokalnym `+02:00`. Każda strona ma widoczny disclaimer „dane syntetyczne demo”.

## Narracja raportu

Raport ma odpowiadać na trzy pytania w kolejności: gdzie jest krytycznie, dlaczego tam jest krytycznie, co robimy. Dlatego mapa sama nie wystarczy. Musi być powiązana z rankingiem, planem zasobów, kolejką OSP i SPO-3. W demo unikaj przewijania po wielu tabelach; używaj bookmarków: `Kraj`, `Wojewoda`, `Gmina`, `What-if`.

## Strona techniczna — jakość i odświeżanie

Dodaj ukrytą stronę dla prezentera i administratora: status odświeżenia tabel, liczba rekordów w kluczowych źródłach, ostatni snapshot, wersja modelu i informacja o seed=42. Strona pozwala szybko odpowiedzieć na pytanie „czy dane są aktualne?” bez wchodzenia do Lakehouse. Wizualizacje: tabela źródeł, karta `Last refresh`, karta `RT events`, karta `Derived files`, lista błędów odświeżenia.

## Storytelling w raporcie

Na początku demo użyj strony 1 i 2, aby pokazać problem. W środku przejdź na stronę 4 i 3, aby pokazać działanie. Na końcu użyj strony 5 i 6, aby pokazać komunikację i konsekwencję opóźnienia. Każda strona powinna mieć jeden główny komunikat w tytule, np. „14 gmin wymaga natychmiastowej decyzji”, „Optymalizacja zwiększa pokrycie o 23,6 p.p.”, „Awaria +12h rozszerza kryzys do 104 gmin”.

## Dostępność i publikacja

Raport publikuj w aplikacji Power BI z odbiorcami zgodnymi z rolami. Ustaw opisy alternatywne dla map i wykresów. Nie używaj czerwieni jako jedynego nośnika statusu; dodaj tekst `critical/high/elevated`. Wyłącz eksport danych dla stron z osobami priorytetowymi. Wersję publiczną lub szkoleniową publikuj tylko z agregatami i syntetycznym disclaimerem.
