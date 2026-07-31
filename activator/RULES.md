# Data Activator — reguły alertowe

## 1. IZZ_Critical_Gmina
Cel: wykryć gminę przekraczającą próg zagrożenia życia. Źródło: `dynamic_risk_latest` albo tabela KQL z wynikiem IZŻ. Próg 75 odpowiada poziomowi `critical`, bo łączy wysoki IWL, długi brak prądu i mróz.
```kql
GminaRisk | where izz_score >= 75 | project gmina_code, izz_score, vulnerable_without_power
```
Odbiorca: RCB, wojewoda. Treść: „Gmina {gmina_code} przekroczyła IZŻ {izz_score}”. Akcja: odprawa i plan zasobów. SPO: SPO-12, SPO-5 przesłankowo.

## 2. CareFacility_Autonomy_Low
Cel: ochronić DPS/ZOL/szpital przed utratą zasilania. Źródło: `dim_care_facility` + `OutageEvents`. Próg <2h, bo to minimalne okno na wysłanie agregatu albo ewakuację.
```kql
CareFacilities | where has_generator == false or generator_autonomy_hours < 2
```
Odbiorca: wojewoda, koordynator medyczny. Akcja: agregat lub ewakuacja. SPO: ochrona ludności, SPO-12.

## 3. PriorityPerson_NoContact
Cel: eskalować brak potwierdzenia kontaktu. Próg 6h, bo po kilku godzinach bez prądu i łączności rośnie ryzyko dla tlenoterapii i seniorów.
```kql
PriorityPersons | join kind=leftouter WelfareCheck on person_token | where isnull(event_time) or event_time < ago(6h)
```
Odbiorca: gmina, OSP, koordynator medyczny. Akcja: wizyta lub patrol.

## 4. SevereCold_NoPower
Cel: uruchomić ogrzewanie awaryjne. Próg -20°C odczuwalnej, bo przy mrozie i wietrze ryzyko wychłodzenia rośnie gwałtownie.
```kql
WeatherReadings | where feels_like_c < -20 | join kind=inner CurrentOutageByGmina() on $left.powiat_code == $right.gmina_code
```
Odbiorca: wojewoda, gmina. Akcja: punkt grzewczy. SPO: SPO-3.

## 5. HeatingPoint_Full
Cel: przeciwdziałać przepełnieniu punktu. Próg 95%, bo powyżej tej wartości spada bezpieczeństwo i komfort, a kolejni mieszkańcy wymagają skierowania gdzie indziej.
```kql
HeatingPointStatus | summarize arg_max(event_time, *) by heating_point_id | extend fill=occupancy*1.0/capacity | where fill >= 0.95
```
Odbiorca: gmina, wojewoda. Akcja: otwarcie rezerwowego punktu.

## 6. Telecom_Blackout
Cel: wykryć gminę bez skutecznej komunikacji. Próg coverage <20% przez >2h, bo SMS/RSO przestają być wystarczające.
```kql
TelecomCoverage | where coverage_pct < 0.2 | summarize duration=count() by gmina_code, bin(event_time, 2h)
```
Odbiorca: SPO-3, gmina. Akcja: radio, OSP door-to-door.

## 7. Alert_Delivery_Low
Cel: mierzyć, czy ostrzeżenie dotarło. Próg <60%, bo poniżej tej wartości większość mieszkańców może nie znać lokalizacji pomocy.
```kql
AlertDelivery | summarize sent=sum(messages_sent), delivered=sum(messages_delivered) by gmina_code | extend rate=delivered*100.0/sent | where rate < 60
```
Odbiorca: rzecznik, RCB, wojewoda. Akcja: retry kanałami alternatywnymi. SPO: SPO-3.

## 8. Cascade_Detected
Cel: rozpoznać awarię kaskadową, nie pojedyncze uszkodzenie. Próg wzrostu 50 tys. odbiorców w 2h uzasadnia eskalację.
```kql
OutageEvents | summarize customers=sum(customers_without_power) by bin(event_time, 2h) | extend jump=customers-prev(customers) | where jump > 50000
```
Odbiorca: RCB, energetyka, RZZK. Akcja: koordynacja krajowa.

## Zasady strojenia progów

Progi w demo są ustawione konserwatywnie, aby pokazać proces. W produkcji powinny być zatwierdzone przez RCB, wojewodów, medyków i operatorów infrastruktury. Każda reguła musi mieć właściciela, czas obowiązywania, kanał eskalacji i procedurę wyciszenia alarmu. Alarm bez rekomendowanej akcji jest szumem; dlatego każda reguła w tym dokumencie wskazuje odbiorcę i następny krok.

## Test reguł

Przed pokazem uruchom test na danych historycznych D0–D+2. Sprawdź, czy `IZZ_Critical_Gmina` wyzwala się dla gmin krytycznych, `Alert_Delivery_Low` znajduje gminy poniżej 60%, a `HeatingPoint_Full` nie alarmuje punktów zamkniętych. Wyniki testów zapisz jako część checklisty gotowości demo.
