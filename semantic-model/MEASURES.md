# Miary DAX

Poniższe miary są projektowane do modelu `WinterShield_SemanticModel`. Format ustawiaj w Power BI zgodnie z opisem.

## 1. Osoby wrażliwe bez zasilania
```dax
Vulnerable Without Power =
SUM(dynamic_risk_latest[vulnerable_without_power])
```
Format: liczba całkowita. Biznesowo: skala populacji wymagającej działań ochrony ludności.

## 2. Gminy krytyczne
```dax
Critical Gminas =
CALCULATE(DISTINCTCOUNT(dynamic_risk_latest[gmina_code]), dynamic_risk_latest[life_threat_level] = "critical")
```
Format: liczba. Główna miara odprawy RCB.

## 3. Średni IZŻ
```dax
Average IZZ =
AVERAGE(dynamic_risk_latest[izz_score])
```
Format: 0.0. Trend ryzyka.

## 4. Maksymalny IZŻ
```dax
Max IZZ =
MAX(dynamic_risk_latest[izz_score])
```
Format: 0.0. Najgorsza gmina.

## 5. Osobo-godziny bez zasilania
```dax
Person-Hours Without Power =
SUMX(dynamic_risk_latest, dynamic_risk_latest[vulnerable_without_power] * dynamic_risk_latest[hours_without_power])
```
Format: liczba. Skala kumulacji cierpienia/ryzyka.

## 6. Pokrycie punktami grzewczymi
```dax
Heating Point Coverage % =
DIVIDE(SUM(selected_heating_points[covered_vulnerable_est]), SUM(dynamic_risk_latest[vulnerable_without_power]))
```
Format: procent 0.0%.

## 7. Przydzielone agregaty
```dax
Generators Assigned =
CALCULATE(COUNTROWS(selected_heating_points), selected_heating_points[generator_assigned] = TRUE())
```
Format: liczba.

## 8. Poprawa pokrycia p.p.
```dax
Coverage Improvement pp =
[Heating Point Coverage %] - 0.131
```
Format: p.p. Demo baseline „po równo” = 13,1%.

## 9. Skuteczność alertów
```dax
Alert Delivery % =
DIVIDE(SUM(alert_delivery[messages_delivered]), SUM(alert_delivery[messages_sent]))
```
Format: procent.

## 10. Otwarcia alertów
```dax
Alert Open % =
DIVIDE(SUM(alert_delivery[messages_opened]), SUM(alert_delivery[messages_delivered]))
```
Format: procent.

## 11. Gminy z dostarczeniem <60%
```dax
Gminas Alert Below 60 % =
COUNTROWS(FILTER(SUMMARIZE(alert_delivery, alert_delivery[gmina_code], "rate", DIVIDE(SUM(alert_delivery[messages_delivered]), SUM(alert_delivery[messages_sent]))), [rate] < 0.6))
```
Format: liczba.

## 12. Priorytetowy kontakt potwierdzony
```dax
Priority Contact Confirmed % =
DIVIDE(CALCULATE(COUNTROWS(welfare_check), welfare_check[result] = "contact_confirmed"), DISTINCTCOUNT(fact_priority_persons[person_token]))
```
Format: procent.

## 13. Ewakuacje
```dax
Evacuations =
CALCULATE(COUNTROWS(welfare_check), welfare_check[result] = "evacuation")
```
Format: liczba.

## 14. Brak kontaktu
```dax
No Contact Visits =
CALCULATE(COUNTROWS(welfare_check), welfare_check[result] = "no_contact")
```
Format: liczba.

## 15. Punkty pełne
```dax
Heating Points Full =
COUNTROWS(FILTER(heating_point_status, DIVIDE(heating_point_status[occupancy], heating_point_status[capacity]) >= 0.95))
```
Format: liczba.

## 16. Placówki z autonomią <2h
```dax
Care Facilities Under 2h Autonomy =
CALCULATE(COUNTROWS(dim_care_facility), dim_care_facility[has_generator] = FALSE() || dim_care_facility[generator_autonomy_hours] < 2)
```
Format: liczba.

## 17. Aktywne awarie
```dax
Active Outage Customers =
SUMX(FILTER(outage_events, outage_events[status] <> "restored"), outage_events[customers_without_power])
```
Format: liczba.

## 18. Średnie pokrycie telco
```dax
Average Telecom Coverage =
AVERAGE(telecom_coverage[coverage_pct])
```
Format: procent.

## 19. Zgłoszenia P1
```dax
Emergency Calls P1 =
CALCULATE(COUNTROWS(emergency_calls), emergency_calls[priority] = "P1")
```
Format: liczba.

## 20. What-if gminy dodatkowe
```dax
WhatIf Additional Critical Gminas =
CALCULATE(DISTINCTCOUNT(whatif_extended_outage[gmina_code]), whatif_extended_outage[whatif_izz] >= 75)
    - [Critical Gminas]
```
Format: liczba.
