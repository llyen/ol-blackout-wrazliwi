# Etyka i prywatność

## Dlaczego ten dokument jest kluczowy

Scenariusz dotyka danych, które w prawdziwym wdrożeniu należałyby do najbardziej wrażliwych: stan zdrowia, zależność od urządzeń medycznych, samotność seniorów, niepełnosprawność, bezdomność i ubóstwo energetyczne. Demo nie używa prawdziwych danych, ale pokazuje proces, który w rzeczywistości wymagałby bardzo silnych podstaw prawnych, minimalizacji, kontroli dostępu i nadzoru człowieka.

## Podstawy prawne

W realnym wdrożeniu przetwarzanie mogłoby opierać się na RODO art. 6 ust. 1 lit. d (żywotne interesy osoby), lit. e (zadanie realizowane w interesie publicznym) oraz właściwych przepisach krajowych o zarządzaniu kryzysowym, ochronie ludności, ratownictwie i ochronie zdrowia. Dane szczególnych kategorii, np. zdrowotne, wymagają przesłanki z art. 9 RODO, w szczególności ochrony żywotnych interesów, interesu publicznego w dziedzinie zdrowia publicznego albo innych podstaw wskazanych w przepisach szczególnych. Każdy przypadek wymaga analizy prawnej i DPIA.

## Privacy-by-design w demie

Demo stosuje agregację do poziomu gminy w `fact_population_vulnerability.csv`. Wskaźniki mówią, ile osób lub jaki odsetek populacji jest wrażliwy, ale nie ujawniają tożsamości. `fact_priority_persons.csv` jest wyraźnie fikcyjny: ma token `PRIO-xxxxx`, fikcyjny kontakt i etykietę `Highly Confidential - synthetic priority person`. To pokazuje mechanikę, nie realny rejestr.

## Kiedy dopuszczalny jest rejestr osób priorytetowych

Taki rejestr może być dopuszczalny tylko wtedy, gdy istnieje konkretna podstawa prawna, jasno określony cel ochrony życia i zdrowia, minimalny zakres danych, ograniczony krąg odbiorców, retencja i audyt. Rejestr nie może stać się ogólną bazą osób „problemowych”. Powinien być aktywowany na czas zagrożenia albo utrzymywany jako zasób gotowości wyłącznie na podstawie prawa, zgód lub innych przesłanek przewidzianych przepisami.

## Kontrola dostępu

Poziom krajowy powinien widzieć agregaty i trendy. Wojewoda widzi swoje województwo. Gmina widzi własny obszar. OSP widzi tylko przydzielone wizyty i minimalny opis działania. Koordynator medyczny widzi kategorię ryzyka i autonomię urządzenia, ale nie więcej niż potrzebne. Technicznie: RLS po `voivodeship_code` i `gmina_code`, Entra ID, Purview sensitivity labels, maskowanie kontaktów, audyt odczytu i write-back.

## Retencja i usuwanie danych

Dane indywidualne powinny mieć najkrótszą możliwą retencję: okres zdarzenia, rozliczalność działań i obowiązki archiwalne wynikające z prawa. Po zakończeniu fazy reagowania należy przeprowadzić przegląd: co usunąć, co zanonimizować, co zachować jako agregat do odbudowy i nauki. Retencja powinna być automatyczna, z wyjątkami zatwierdzanymi formalnie.

## Ryzyka nadużyć i zabezpieczenia

Ryzyka: profilowanie osób ubogich lub chorych, nieuprawniony dostęp, stygmatyzacja gmin, użycie danych do celów innych niż ratowanie życia, nadmierna automatyzacja decyzji. Zabezpieczenia: ograniczenie celu, rozdzielenie ról, rejestr dostępu, regularne przeglądy, testy RLS, zasada dwóch par oczu dla eksportów, zakaz pobierania pełnych list na poziomie krajowym, procedura naruszeń.

## Rola człowieka

Algorytm nie zastępuje wojewody, wójta, dyrektora RCB ani koordynatora medycznego. Ranking jest rekomendacją. Decyzja o ewakuacji, wydaniu agregatu, kontakcie z osobą i uruchomieniu SPO pozostaje po stronie uprawnionego człowieka. Interfejs powinien pokazywać uzasadnienie: IWL, temperatura, godziny bez prądu, łączność, czas dojazdu.

## Transparentność wobec obywatela

Obywatel powinien wiedzieć, że w sytuacji kryzysowej administracja może przetwarzać minimalne dane w celu ochrony życia. Tam, gdzie to możliwe, należy zapewnić informację, kanał korekty danych i wyjaśnienie decyzji. W trybie pilnym obowiązki informacyjne mogą być realizowane po ustaniu bezpośredniego zagrożenia, zgodnie z prawem.

## Rekomendacje dla realnego wdrożenia

1. Wykonać DPIA przed pilotażem.
2. Zacząć od agregatów gminnych i dopiero potem list priorytetowych.
3. Uzgodnić źródła danych z NFZ, opieką społeczną i gminami.
4. Wdrożyć RLS, Purview, audyt i DLP przed pierwszym testem z danymi realnymi.
5. Zaprojektować tryb offline i awaryjny bez dostępu do chmury.
6. Prowadzić regularne ćwiczenia i przegląd błędów algorytmu.
7. Publikować jasne komunikaty dla obywateli o celu i zakresie przetwarzania.

## Minimalizacja w praktyce

Minimalizacja oznacza, że inne dane widzi RCB, inne wojewoda, a inne druh OSP. RCB potrzebuje liczby gmin krytycznych, osób wrażliwych bez zasilania i trendu. Wojewoda potrzebuje planu zasobów. Gmina potrzebuje listy działań lokalnych. Druh OSP potrzebuje tylko tyle, aby wykonać wizytę: token, kategoria operacyjna, adres lub punkt kontaktu w realnym systemie, instrukcja i wynik do zaznaczenia. Dane medyczne szczegółowe nie powinny być przenoszone do aplikacji terenowej, jeżeli wystarczy kategoria ryzyka.

## Audyt i odpowiedzialność

Każdy odczyt danych indywidualnych powinien być audytowany: kto, kiedy, z jakiej roli, dla jakiej gminy i w jakim celu. Każda decyzja write-back powinna zawierać uzasadnienie i identyfikator operatora. Audyt nie służy karaniu ratowników za decyzje podejmowane w stresie, ale ochronie obywateli przed nadużyciem oraz administracji przed brakiem rozliczalności.

## Zakaz wtórnego wykorzystania

Dane zebrane dla ochrony życia w blackoucie nie mogą być użyte do innych celów: kontroli socjalnej, typowania osób do innych postępowań, oceny „zaradności” gminy ani komunikacji politycznej. Raporty po zdarzeniu powinny używać agregatów i anonimizacji. Dostęp badawczy wymaga osobnej podstawy, anonimizacji i zgody właściciela danych.
