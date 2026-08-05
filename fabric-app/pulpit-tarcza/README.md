# Pulpit „Tarcza Zimowa" — aplikacja Fabric

> Demonstracja. Wszystkie dane są syntetyczne. Osoby, adresy i zdarzenia nie istnieją.

Aplikacja decyzyjna dla scenariusza długotrwałego blackoutu zimowego. Odpowiada na jedno
pytanie, którego nie da się zadać tabeli w Excelu: **do kogo trzeba dojechać najpierw i
ile zostało czasu**. Prowadzi od obrazu krajowego, przez kolejkę priorytetową osób
zależnych od zasilania, po potwierdzenie wizyty w terenie i ostrzeżenie ludności.

## Wdrożenie

| Element | Wartość |
|---|---|
| Adres | _(uzupełnić po `rayfin up`)_ |
| Workspace | `OL-ZK-Demo-Blackout` |
| Pojemność | `fcdemo` (F8, West Europe, `rg-fabric-cap-demo`) |
| Dzierżawa | `7ada8cf4-c4be-488f-a844-6d37ee64849e` |

```powershell
# Pojemnosc sama sie pauzuje - najpierw ja obudz
az resource show -g rg-fabric-cap-demo -n fcdemo --resource-type Microsoft.Fabric/capacities --query properties.state -o tsv
az resource invoke-action -g rg-fabric-cap-demo -n fcdemo --resource-type Microsoft.Fabric/capacities --action resume

npx rayfin login -t 7ada8cf4-c4be-488f-a844-6d37ee64849e
npx rayfin up -y
npx rayfin up db apply --force
```

Po pierwszym wdrożeniu trzeba dopisać otrzymany adres do `allowedRedirectUris`
w `rayfin/rayfin.yml` i wdrożyć ponownie — inaczej logowanie wróci na pustą stronę.

## Architektura danych

Aplikacja ma dwie rozdzielne warstwy.

**Odczyt — scena statyczna.** `tools/build_scene.py` czyta zbiory z `datasets/` i generuje
jeden plik `public/data/scene.json`: 97 klatek godzinowych obejmujących 14–18.01.2026,
wskaźnik IZŻ dla każdej gminy w każdej godzinie, punkty grzewcze, agregaty osób wrażliwych
i zasięg łączności. Aplikacja pobiera go raz przy starcie. Demonstracja jest przez to
deterministyczna, działa bez pojemności Fabric i nie obciąża Lakehouse przy kliknięciu.

**Zapis — encje Rayfin.** Wynik wizyty kontrolnej, raport z punktu grzewczego, kampania
ostrzegawcza. Żadna nie ma akcji `delete`: korekta to nowy wiersz. Kto, kiedy i na jakiej
podstawie zdecydował — musi dać się odtworzyć.

Bez skonfigurowanego backendu zapisy trafiają do pamięci przeglądarki, więc aplikację da
się pokazać także offline; sygnalizuje to pasek nad treścią.

## Czas jako strumień na żywo

Scena jest statyczna, ale prezentowana jak dane napływające na bieżąco. Klatkę wylicza
`liveFrameIndex` z zegara ściennego (0,5 min zegara = 1 godzina scenariusza, pełny przebieg
≈ 48 minut), a punkt zaczepienia liczony jest **od epoki, nie od uruchomienia aplikacji**.

Ma to trzy konsekwencje, wszystkie zamierzone:

- demonstracja wygląda tak samo o 9 rano i o 23 — nie trzeba jej „ustawiać" przed pokazem,
- odświeżenie strony nie cofa przebiegu do początku,
- dwie osoby patrzące na aplikację w tej samej chwili widzą tę samą godzinę scenariusza.

## Wskaźnik IZŻ

Indeks Zagrożenia Życia łączy pięć składowych w jedną liczbę 0–100 na gminę:

| Składowa | Waga | Znaczenie |
|---|---|---|
| IWL | 0,38 | udział osób zależnych od zasilania i wsparcia |
| awaria zasilania | 0,30 | czas trwania i zasięg braku prądu |
| temperatura | 0,18 | temperatura odczuwalna |
| łączność | 0,09 | zasięg sieci — bez niego ostrzeżenie nie dociera |
| dojazd | 0,05 | czas dojazdu służb |

Formuła istnieje w dwóch miejscach: w notatniku `03_dynamic_risk.py` (warstwa danych) i w
`tools/build_scene.py` (warstwa aplikacji). Żeby nie rozjechały się po cichu, test
`src/__tests__/model.test.ts` sprawdza kotwicę: klatka odpowiadająca chwili notatnika musi
dać szczyt **82,82**. Jeśli ten test padnie, formuły się rozeszły.

## Ekrany

| Ekran | Co pokazuje | Decyzja użytkownika |
|---|---|---|
| Obraz krajowy | mapa IZŻ, wskaźniki, oś czasu awarii, prognoza pogorszenia | ogłoszenie stopnia alarmowego, skierowanie sił |
| Osoby wrażliwe | agregaty wg województw i kategorii zależności, gminy o najwyższym IZŻ | wskazanie obszarów priorytetowych |
| Wizyty kontrolne | kolejka priorytetowa wg pozostałej autonomii zasilania, trasy zespołów | zapis wyniku wizyty, decyzja o ewakuacji |
| Punkty grzewcze | obłożenie, zapas paliwa, checklista otwarcia | otwarcie punktu, zgłoszenie potrzeb |
| Ostrzeganie | zasięg kampanii, gminy bez łączności, podpowiedź treści | zatwierdzenie i wysyłka komunikatu SPO-3 |

## Ochrona danych

Widok krajowy (rola RCB) **nie ma dostępu do listy osób** — pracuje wyłącznie na
agregatach. Lista imienna jest widoczna dopiero dla gminy, zespołu OSP i koordynatora
medycznego, i tylko w granicach ich przydziału. Sprawdza to `canSeePersonList` i
`canActOn`, obie objęte testami. To nie jest ozdobnik: pokazanie, że system celowo
zawęża widoczność, jest częścią narracji demonstracji.

Osoby identyfikuje token (`PRIO-00001`), nie dane osobowe.

## Tryb terenowy

Zespół w terenie może stracić łączność. Formularz wizyty działa wtedy dalej, a zapis
dostaje identyfikator synchronizacji nadany na urządzeniu. Po odzyskaniu łączności ta
sama paczka wysłana ponownie **nie tworzy drugiej wizyty** — `dedupeVisits` zostawia
najnowszy zapis dla danego identyfikatora. Zapisy bez identyfikatora nie są scalane.

## Mapa

`src/components/CountryMap.tsx` rysuje granice 16 województw i pozwala je przeglądać:
kółko myszy lub gest szczypania przybliża w miejscu kursora, przeciągnięcie przesuwa,
dwuklik przybliża dwukrotnie, przyciski w rogu i klawisze `+`, `−`, `0` oraz strzałki
robią to samo z klawiatury.

`BOUNDS` musi być identyczne w `CountryMap.tsx`, `src/data/model.ts` i
`tools/build_poland_geo.py` — inaczej znaczniki rozjadą się z granicami.

## Kolorystyka

Jasna paleta rządowa (gov.pl / MSWiA), tokeny `--color-gov*` w `src/main.css`.
Czerwień `#d5233f` jest **poza tokenami marki** — w pulpicie kryzysowym koduje powagę
sytuacji, więc użyta w nagłówku traciłaby siłę sygnału.

Skala powagi ma cztery rozróżnialne stopnie: `#15803d` → `#a16207` → `#c2410c` → `#d5233f`.
Test pilnuje, żeby żadne dwa poziomy nie miały tej samej barwy — przy przemalowaniu
z ciemnego motywu odwzorowanie barw raz już skleiło dwa sąsiednie stopnie i nic tego
nie zgłosiło poza okiem.

## Skrypty

| Polecenie | Opis |
|---|---|
| `npm run dev` | wdrożenie do Fabric i lokalny serwer |
| `npm run build` | budowanie produkcyjne |
| `npm run test` | testy (Vitest) |
| `npm run rayfin:up` | wdrożenie do Fabric bez serwera lokalnego |
| `npm run rayfin:db` | migracje bazy |
| `python tools/build_scene.py` | przebudowa `public/data/scene.json` |
| `python tools/build_poland_geo.py` | przebudowa granic województw |

## Testy

39 testów w trzech plikach:

- `model.test.ts` — kotwica IZŻ, rozróżnialność skali powagi, niezależność zegara od pory
  uruchomienia, zakres widoczności ról, walidacje trzech formularzy, scalanie zapisów offline,
- `geography.test.ts` — spójność `BOUNDS` i odwzorowania współrzędnych,
- `AuthProvider.test.tsx` — bramka logowania.
