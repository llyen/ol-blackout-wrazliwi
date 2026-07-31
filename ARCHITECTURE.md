# Architektura rozwiązania

## Założenie operacyjne

System ma wspierać reagowanie na blackout zimowy, dlatego musi łączyć warstwę wsadową (rejestry, wymiary, zasoby, wrażliwość) z warstwą strumieniową (pogoda, awarie, 112, łączność). W scenariuszu Eventstream przyjmuje **735602 zdarzeń RT** z czterech głównych strumieni, a Lakehouse przechowuje 2477 gmin, 900 placówek, 500 punktów grzewczych i 420 agregatów.

## Warstwa danych wsadowych — Lakehouse

Lakehouse jest właściwym miejscem dla danych referencyjnych: TERYT, placówki, punkty grzewcze, agregaty, czynniki IWL i wyniki notebooków. Te dane są relatywnie stabilne, wymagają wersjonowania i współdzielenia z Power BI, Fabric Apps i Data Agent. W produkcji Lakehouse pozwoliłby też trzymać snapshoty planów ochrony ludności i zestawy gotowości wojewodów.

## Warstwa real-time — Eventstream i Eventhouse

Eventstream pełni rolę bramy telemetrii. Eventhouse/KQL jest użyty, bo zapytania typu „ostatni status gminy”, „wzrost awarii w 2h”, „BTS poniżej 20% przez 2h” i „zgłoszenia P1 w ostatniej dobie” są naturalnymi zapytaniami czasowymi. KQL pozwala budować funkcje `CurrentOutageByGmina()` i zasilać Real-Time Dashboard bez każdorazowego przeliczania w Power BI.

## Warstwa analityczna — Notebooki

Notebooki są miejscem obliczeń, których nie chcemy wykonywać w każdym odświeżeniu raportu: IWL, IZŻ, greedy maximal covering dla punktów grzewczych, nearest-neighbour routing OSP i what-if. Wyniki zapisują się do `datasets\derived\` i w Fabric trafiłyby do tabel Lakehouse. Latencja tej warstwy jest minutowa, co jest wystarczające dla decyzji o zasobach.

## Warstwa decyzyjna — Power BI i Real-Time Dashboard

Power BI pokazuje obraz krajowy, ranking i drill-through do gminy. Real-Time Dashboard pokazuje dyżurnemu bieżącą telemetrię: awarie, zgłoszenia, łączność i punkty grzewcze. Podział jest celowy: Power BI jest dla odpraw i decyzji, dashboard KQL dla dyżuru operacyjnego.

## Warstwa działania — Fabric App, Activator, Data Agent

Fabric App zamyka pętlę write-back: wojewoda zatwierdza plan, gmina raportuje punkt grzewczy, OSP rejestruje wynik wizyty, a SPO-3 uruchamia kampanię komunikacyjną. Activator wyzwala alerty progowe. Data Agent odpowiada na pytania ad hoc, ale nie ujawnia danych osobowych.

## Latencje i wolumeny

- Strumienie wejściowe: 735602 zdarzeń dla pogody, awarii, 112 i telco.
- KQL: sekundy dla zapytań o ostatni stan i korelacje.
- Notebooki: minuty dla pełnego przeliczenia IWL/IZŻ/optymalizacji.
- Power BI: odświeżenie zgodne z harmonogramem lub DirectQuery/KQL dla wybranych kafli.
- Aplikacja terenowa: write-back natychmiast online albo kolejkowany offline.

## Co byłoby inaczej w prawdziwym wdrożeniu

**Integracje:** dane awarii pochodziłyby od OSD/PSE, pogoda z IMGW, dane medyczne z prawnie umocowanych źródeł NFZ/świadczeniodawców, a pomoc społeczna z systemów gminnych i powiatowych. Niezbędne byłyby umowy, API, słowniki jakości danych i proces potwierdzania aktualności.

**Bezpieczeństwo i klasyfikacja:** wymagane są Private Link, Managed Identity, Key Vault, etykiety Purview, RLS, audyt, DLP i procedury dostępu awaryjnego. Dane indywidualne nie powinny trafiać do raportu krajowego.

**Ciągłość działania przy blackoucie:** system wspierający blackout sam musi działać przy blackoucie. Oznacza to chmurę z redundancją regionów, awaryjne łącza, offline cache dla gmin/OSP, eksport paczek CSV/PDF, procedury papierowe, zasilanie zapasowe stanowisk dyżurnych i regularne ćwiczenia przełączenia.

**Governance:** w produkcji potrzebne są DPIA, właściciele danych, katalog danych, klasyfikacja informacji, retencja, testy odporności i przegląd algorytmów. Model wskazuje priorytety, ale decyzja pozostaje u człowieka.

## Uzasadnienie wyborów technicznych

Eventhouse jest preferowane dla telemetrii, bo zapytania operacyjne są oknami czasowymi: ostatni status, przyrost w 2 godziny, brak łączności przez 2 godziny, zgłoszenia w ostatniej dobie. Lakehouse jest preferowane dla rejestrów, bo dane referencyjne wymagają wersjonowania, jakości, lineage i wygodnego zasilenia modelu semantycznego. Notebooki są właściwe dla algorytmów, bo IWL, IZŻ, covering i routing wymagają przeliczeń wsadowych oraz zapisu wyników, a nie tylko prostych agregacji.

## Granice odpowiedzialności komponentów

Eventstream nie interpretuje ryzyka — tylko dostarcza zdarzenia. KQL wykrywa korelacje krótkookresowe i zasila dyżurnego. Notebooki tworzą rekomendacje i rankingi. Power BI tłumaczy sytuację decydentowi. Fabric App zapisuje decyzje i meldunki. Activator budzi człowieka, gdy przekroczony jest próg. Data Agent odpowiada na pytania, ale nie omija RLS i nie podejmuje decyzji.

## Odporność organizacyjna

Architektura musi mieć odpowiednik proceduralny: kto uruchamia tryb offline, kto eksportuje paczki dla gmin, kto potwierdza ostatni poprawny snapshot i kto ma prawo zatwierdzić użycie danych indywidualnych. W ćwiczeniu należy sprawdzić nie tylko dashboard, ale również scenariusz utraty łączności u wojewody, brak Power BI, niedostępność Eventstream oraz ręczny tryb SPO-3 przez radio lokalne i OSP.
