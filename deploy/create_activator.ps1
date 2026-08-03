<#
.SYNOPSIS
    Tworzy Activator scenariusza „Tarcza Zimowa" i wdraza reguly alertowe jako funkcje KQL.

.DESCRIPTION
    Skrypt jest idempotentny:
      - wyszukuje albo tworzy element Reflex/Activator OL_BLK_Activator,
      - tworzy/aktualizuje funkcje KQL alert_* w Eventhouse wg activator\RULES.md,
      - weryfikuje liczbe trafien i wypisuje przykladowe rekordy.

    Wszystkie funkcje zwracaja ten sam zestaw kolumn kontraktowych
    (alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value,
    spo, message), dzieki czemu Activator albo KQL alert moze je obsluzyc jednym
    szablonem powiadomienia, niezaleznie od reguly.

    Uwaga o czasie: scenariusz odtwarza sie w tempie 60x, wiec godzina akcji trwa
    minute zegara. Progi czasowe z RULES.md przeliczam na minuty zegara i zapisuje
    to w docstring kazdej funkcji, zeby przy pokazie nie bylo watpliwosci, dlaczego
    reguly patrza na tak krotkie okna.

    Powiadomienia Activatora dokancza sie w UI - publiczne API Fabric nie wystawia
    jeszcze definicji regul powiadomien.

.EXAMPLE
    .\deploy\create_activator.ps1 -WorkspaceName OL-ZK-Demo-Blackout
#>
[CmdletBinding()]
param(
    [string]$WorkspaceName = 'OL-ZK-Demo-Blackout',
    [string]$ActivatorName = 'OL_BLK_Activator',
    [string]$WorkspaceId = '68e1369e-bc4d-4c87-a747-e3fd78c21f21',
    [string]$ClusterUri = 'https://trd-bv9kuej96btp7bpuq7.z6.kusto.fabric.microsoft.com',
    [string]$KqlDatabaseName = 'OL_BLK_Eventhouse'
)

$ErrorActionPreference = 'Stop'
$FabricApi = 'https://api.fabric.microsoft.com/v1'

function Write-Step($msg) { Write-Host "`n=== $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "  $msg" -ForegroundColor Gray }
function Write-Warn($msg) { Write-Host "  [UWAGA] $msg" -ForegroundColor Yellow }

function Get-Token([string]$resource) {
    az account get-access-token --resource $resource --query accessToken -o tsv
}

function Get-FabricHeaders {
    @{ Authorization = "Bearer $(Get-Token 'https://api.fabric.microsoft.com')"; 'Content-Type' = 'application/json' }
}

function Get-KustoHeaders {
    @{ Authorization = "Bearer $(Get-Token 'https://kusto.kusto.windows.net')"; 'Content-Type' = 'application/json' }
}

function Resolve-Workspace {
    $ws = (Invoke-RestMethod -Uri "$FabricApi/workspaces" -Headers (Get-FabricHeaders)).value |
          Where-Object displayName -eq $WorkspaceName | Select-Object -First 1
    if ($ws) { return $ws.id }
    if ($WorkspaceId) {
        Write-Warn "Nie znaleziono workspace '$WorkspaceName' po nazwie; uzywam id $WorkspaceId."
        return $WorkspaceId
    }
    throw "Nie znaleziono workspace '$WorkspaceName'."
}

function Invoke-FabricWebRequest([string]$method, [string]$uri, $body = $null) {
    $json = if ($null -ne $body) { $body | ConvertTo-Json -Depth 100 } else { $null }
    $response = Invoke-WebRequest -Method $method -Uri $uri -Headers (Get-FabricHeaders) -Body $json -ContentType 'application/json' -SkipHttpErrorCheck
    if ($response.StatusCode -eq 202) {
        $operationUrl = $response.Headers.Location | Select-Object -First 1
        if ($operationUrl) {
            do {
                Start-Sleep -Seconds 5
                $operation = Invoke-RestMethod -Method Get -Uri $operationUrl -Headers (Get-FabricHeaders)
                Write-Info "operacja Fabric: $($operation.status)"
            } while ($operation.status -in 'NotStarted', 'Running')
            if ($operation.status -notin 'Succeeded', 'Completed') {
                throw "Operacja Fabric nie powiodla sie: $($operation | ConvertTo-Json -Depth 20)"
            }
        }
    }
    if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
        throw "Fabric REST $method $uri zwrocil $($response.StatusCode): $($response.Content)"
    }
    return $response
}

function Get-OrCreateActivator([string]$workspaceId) {
    $item = (Invoke-RestMethod -Uri "$FabricApi/workspaces/$workspaceId/items" -Headers (Get-FabricHeaders)).value |
            Where-Object { $_.displayName -eq $ActivatorName -and $_.type -eq 'Reflex' } |
            Select-Object -First 1
    if ($item) { Write-Ok "Activator juz istnieje: $($item.id)"; return $item }

    $response = Invoke-FabricWebRequest -method Post -uri "$FabricApi/workspaces/$workspaceId/reflexes" -body @{
        displayName = $ActivatorName
        description = 'Reguly alertowe scenariusza blackout i ludnosc wrazliwa wg activator\RULES.md'
    }
    $created = $response.Content | ConvertFrom-Json
    Write-Ok "utworzono Activator: $($created.id)"
    return $created
}

function Invoke-KustoMgmt([string]$command) {
    $body = @{ db = $KqlDatabaseName; csl = $command } | ConvertTo-Json -Depth 20
    Invoke-RestMethod -Method Post -Uri "$ClusterUri/v1/rest/mgmt" -Headers (Get-KustoHeaders) -Body $body | Out-Null
}

function Invoke-KustoQuery([string]$query) {
    $body = @{ db = $KqlDatabaseName; csl = $query } | ConvertTo-Json -Depth 20
    $response = Invoke-RestMethod -Method Post -Uri "$ClusterUri/v2/rest/query" -Headers (Get-KustoHeaders) -Body $body
    $response | Where-Object TableKind -eq 'PrimaryResult'
}

# Progi sa zgodne z activator\RULES.md. Kazda funkcja zwraca kolumny kontraktowe,
# zeby powiadomienie i lista alertow mialy jeden format niezaleznie od reguly.
$FunctionCommands = @'
.create-or-alter function with (folder='Activator/Blackout', docstring='Alert: gmina przekroczyla indeks zagrozenia zycia IZZ 75. Indeks liczony w locie z trzech skladowych: udzial ludnosci wrazliwej bez pradu, czas trwania awarii i temperatura odczuwalna. Dzieki temu regula dziala na strumieniu, nie na tabeli wsadowej z Lakehouse.') alert_izz_critical() {
let okno = 15m;
let awarie = OutageEvents
    | where event_time > ago(okno)
    | summarize poczatek = min(event_time), arg_max(event_time, status, customers_without_power, cascade_stage) by gmina_code
    | where status != 'restored'
    | extend godziny_awarii = todouble(datetime_diff('minute', event_time, poczatek));
let pogoda = WeatherReadings
    | where event_time > ago(okno)
    | summarize arg_max(event_time, feels_like_c) by powiat_code;
awarie
| join kind=inner (PopulationVulnerability | project gmina_code, population, vulnerable_population_est, rescue_travel_time_min) on gmina_code
| join kind=inner (dim_gmina | project gmina_code, gmina_name, powiat_code) on gmina_code
| join kind=leftouter pogoda on powiat_code
| extend udzial_bez_pradu = min_of(todouble(customers_without_power) / todouble(max_of(population, 1)), 1.0)
| extend vulnerable_without_power = tolong(vulnerable_population_est * udzial_bez_pradu)
| extend skladnik_ludnosc = 45.0 * udzial_bez_pradu * min_of(todouble(vulnerable_population_est) / todouble(max_of(population, 1)) * 4.0, 1.0)
| extend skladnik_czas = 30.0 * min_of(godziny_awarii / 12.0, 1.0)
| extend skladnik_mroz = 25.0 * min_of(max_of(-1.0 * coalesce(feels_like_c, 0.0) - 10.0, 0.0) / 15.0, 1.0)
| extend izz_score = round(skladnik_ludnosc + skladnik_czas + skladnik_mroz, 1)
| where izz_score >= 75
| extend alert_rule='alert_izz_critical', alert_severity=iff(izz_score >= 85, 'critical', 'warning'), alert_ts=event_time, alert_key=gmina_code, current_value=izz_score, threshold_value=75.0, spo='SPO-12;SPO-5', message=strcat('IZZ KRYTYCZNY - gmina ', gmina_name, ', indeks ', tostring(izz_score), ', ', tostring(vulnerable_without_power), ' osob wrazliwych bez pradu, odczuwalna ', tostring(round(coalesce(feels_like_c, 0.0), 1)), ' C')
| project alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value, spo, message, gmina_code, gmina_name, izz_score, vulnerable_without_power, customers_without_power, godziny_awarii, feels_like_c, rescue_travel_time_min, cascade_stage
| order by current_value desc
}
---NEXT---
.create-or-alter function with (folder='Activator/Blackout', docstring='Alert: placowka opieki bez zasilania rezerwowego albo z autonomia ponizej 2 h. Korzysta z funkcji CareFacilityAutonomyState, ktora laczy rejestr placowek z biezacym stanem awarii.') alert_care_facility_autonomy() {
CareFacilityAutonomyState()
| where recommended_action != 'monitor'
| where has_power_risk == true
| join kind=inner (dim_gmina | project gmina_code, gmina_name) on gmina_code
| extend alert_rule='alert_care_facility_autonomy', alert_severity=iff(recommended_action == 'evacuate' or has_generator == false, 'critical', 'warning'), alert_ts=now(), alert_key=facility_id, current_value=generator_autonomy_hours, threshold_value=2.0, spo='SPO-12', message=strcat('PLACOWKA BEZ ZASILANIA - ', facility_type, ' ', facility_id, ' w gminie ', gmina_name, ', ', tostring(current_occupancy), ' podopiecznych, autonomia ', tostring(round(generator_autonomy_hours, 1)), ' h, zapotrzebowanie ', tostring(round(power_need_kw, 0)), ' kW, rekomendacja: ', recommended_action)
| project alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value, spo, message, facility_id, facility_type, gmina_code, gmina_name, current_occupancy, has_generator, generator_autonomy_hours, power_need_kw, recommended_action
| order by current_value asc, current_occupancy desc
| take 50
}
---NEXT---
.create-or-alter function with (folder='Activator/Blackout', docstring='Alert: osoba priorytetowa bez potwierdzonego kontaktu. Prog produkcyjny z RULES.md: 6 h. Prog demo: 6 min zegara, bo scenariusz biegnie w tempie 60x.') alert_priority_person_nocontact() {
let bez_pradu = OutageEvents
    | where event_time > ago(15m)
    | summarize arg_max(event_time, status) by gmina_code
    | where status != 'restored'
    | project gmina_code;
let odwiedzeni = WelfareCheck
    | where event_time > ago(6m)
    | where result in ('ok', 'assisted', 'evacuated')
    | distinct person_token;
PriorityPersons
| where category in ('dialysis', 'home_oxygen', 'powered_medical_device')
| join kind=inner bez_pradu on gmina_code
| join kind=leftanti odwiedzeni on person_token
| join kind=inner (dim_gmina | project gmina_code, gmina_name) on gmina_code
| extend alert_rule='alert_priority_person_nocontact', alert_severity=iff(medical_device_autonomy_hours < 12, 'critical', 'warning'), alert_ts=now(), alert_key=person_token, current_value=medical_device_autonomy_hours, threshold_value=6.0, spo='SPO-12', message=strcat('BRAK KONTAKTU - osoba ', person_token, ' (', category, ') w gminie ', gmina_name, ', autonomia urzadzenia ', tostring(round(medical_device_autonomy_hours, 1)), ' h, mieszka sama: ', tostring(is_living_alone))
| project alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value, spo, message, person_token, category, gmina_code, gmina_name, age_band, medical_device_autonomy_hours, is_living_alone, fictional_contact
| order by current_value asc
| take 50
}
---NEXT---
.create-or-alter function with (folder='Activator/Blackout', docstring='Alert: mroz odczuwalny ponizej -20 C w gminie bez zasilania. Powiat laczy sie z gmina przez dim_gmina, bo pogoda jest rejestrowana na poziomie powiatu.') alert_severe_cold_nopower() {
let bez_pradu = OutageEvents
    | where event_time > ago(15m)
    | summarize arg_max(event_time, status, customers_without_power) by gmina_code
    | where status != 'restored';
WeatherReadings
| where event_time > ago(15m)
| summarize arg_max(event_time, feels_like_c, temperature_c, wind_kmh) by powiat_code
| where feels_like_c < -20
| join kind=inner (dim_gmina | project gmina_code, gmina_name, powiat_code, population) on powiat_code
| join kind=inner bez_pradu on gmina_code
| extend alert_rule='alert_severe_cold_nopower', alert_severity=iff(feels_like_c < -25, 'critical', 'warning'), alert_ts=event_time, alert_key=strcat(gmina_code, ':', format_datetime(bin(event_time, 1h), 'yyyy-MM-dd HH:mm')), current_value=feels_like_c, threshold_value=-20.0, spo='SPO-3', message=strcat('MROZ BEZ ZASILANIA - gmina ', gmina_name, ', odczuwalna ', tostring(round(feels_like_c, 1)), ' C przy wietrze ', tostring(round(wind_kmh, 0)), ' km/h, ', tostring(customers_without_power), ' odbiorcow bez pradu')
| project alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value, spo, message, gmina_code, gmina_name, powiat_code, feels_like_c, temperature_c, wind_kmh, customers_without_power, population
| order by current_value asc
| take 50
}
---NEXT---
.create-or-alter function with (folder='Activator/Blackout', docstring='Alert: punkt grzewczy powyzej 95 procent pojemnosci. Punkty zamkniete sa pomijane, bo nie przyjmuja mieszkancow.') alert_heating_point_full() {
HeatingPointStatus
| where event_time > ago(15m)
| summarize arg_max(event_time, status, occupancy, capacity, needs_food, needs_medical_support, needs_generator, gmina_code) by heating_point_id
| where capacity > 0 and status != 'closed'
| extend occupancy_pct = round(100.0 * occupancy / capacity, 1)
| where occupancy_pct >= 95
| join kind=leftouter (HeatingPoints | project heating_point_id, heating_point_type, has_generator) on heating_point_id
| join kind=inner (dim_gmina | project gmina_code, gmina_name) on gmina_code
| extend alert_rule='alert_heating_point_full', alert_severity=iff(occupancy_pct >= 100, 'critical', 'warning'), alert_ts=event_time, alert_key=strcat(heating_point_id, ':', format_datetime(bin(event_time, 1h), 'yyyy-MM-dd HH:mm')), current_value=occupancy_pct, threshold_value=95.0, spo='SPO-12', message=strcat('PUNKT GRZEWCZY PELNY - ', heating_point_id, ' (', heating_point_type, ') w gminie ', gmina_name, ', ', tostring(occupancy), '/', tostring(capacity), ' miejsc (', tostring(occupancy_pct), '%)')
| project alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value, spo, message, heating_point_id, heating_point_type, gmina_code, gmina_name, occupancy, capacity, needs_food, needs_medical_support, needs_generator, has_generator
| order by current_value desc
}
---NEXT---
.create-or-alter function with (folder='Activator/Blackout', docstring='Alert: gmina bez skutecznej lacznosci. Prog pokrycia 20 procent utrzymujacy sie w wiekszosci odczytow okna. Prog produkcyjny z RULES.md: 2 h. Prog demo: 2 min zegara przy tempie 60x.') alert_telecom_blackout() {
TelecomCoverage
| where event_time > ago(2m)
| summarize odczyty = count(), ponizej_progu = countif(coverage_pct < 0.2), arg_min(coverage_pct, event_time, bts_total, bts_on_battery, battery_hours_remaining) by gmina_code
| where odczyty > 0 and todouble(ponizej_progu) / todouble(odczyty) >= 0.5
| join kind=inner (dim_gmina | project gmina_code, gmina_name, population) on gmina_code
| extend pokrycie_pct = round(coverage_pct * 100, 1)
| extend alert_rule='alert_telecom_blackout', alert_severity=iff(pokrycie_pct < 5, 'critical', 'warning'), alert_ts=event_time, alert_key=gmina_code, current_value=pokrycie_pct, threshold_value=20.0, spo='SPO-3', message=strcat('BRAK LACZNOSCI - gmina ', gmina_name, ', pokrycie ', tostring(pokrycie_pct), '%, ', tostring(bts_on_battery), ' z ', tostring(bts_total), ' stacji na bateriach, zapas ', tostring(round(battery_hours_remaining, 1)), ' h. Ostrzeganie przez radio i OSP.')
| project alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value, spo, message, gmina_code, gmina_name, population, pokrycie_pct, bts_total, bts_on_battery, battery_hours_remaining
| order by current_value asc, population desc
| take 50
}
---NEXT---
.create-or-alter function with (folder='Activator/Blackout', docstring='Alert: dostarczalnosc ostrzezenia SPO-3 ponizej 60 procent. Bez filtru czasu, bo ostrzeganie poprzedza kaskade i w ruchomym oknie live tych zdarzen juz nie ma.') alert_delivery_low() {
AlertDelivery
| summarize wyslane = sum(messages_sent), dostarczone = sum(messages_delivered), otwarte = sum(messages_opened), alert_ts = max(event_time) by gmina_code
| where wyslane > 0
| extend dostarczalnosc = round(100.0 * dostarczone / wyslane, 1)
| where dostarczalnosc < 60
| join kind=inner (dim_gmina | project gmina_code, gmina_name, population) on gmina_code
| extend alert_rule='alert_delivery_low', alert_severity=iff(dostarczalnosc < 40, 'critical', 'warning'), alert_key=gmina_code, current_value=dostarczalnosc, threshold_value=60.0, spo='SPO-3', message=strcat('OSTRZEZENIE NIE DOTARLO - gmina ', gmina_name, ', dostarczalnosc ', tostring(dostarczalnosc), '% (', tostring(dostarczone), ' z ', tostring(wyslane), ' wiadomosci). Powtorz kanalami alternatywnymi.')
| project alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value, spo, message, gmina_code, gmina_name, population, wyslane, dostarczone, otwarte, dostarczalnosc
| order by current_value asc, population desc
| take 50
}
---NEXT---
.create-or-alter function with (folder='Activator/Blackout', docstring='Alert: awaria kaskadowa. Prog przyrostu 50 tys. odbiorcow bez pradu w oknie odpowiadajacym 2 h akcji, czyli 2 min zegara przy tempie 60x.') alert_cascade_detected() {
OutageEvents
| where event_time > ago(20m)
| summarize odbiorcy = sum(customers_without_power), gminy = dcount(gmina_code), max_etap = max(cascade_stage) by okno = bin(event_time, 2m)
| order by okno asc
| serialize
| extend poprzednio = prev(odbiorcy)
| where isnotnull(poprzednio) and odbiorcy - poprzednio > 50000
| extend przyrost = odbiorcy - poprzednio
| extend alert_rule='alert_cascade_detected', alert_severity='critical', alert_ts=okno, alert_key=format_datetime(okno, 'yyyy-MM-dd HH:mm'), current_value=todouble(przyrost), threshold_value=50000.0, spo='SPO-12', message=strcat('AWARIA KASKADOWA - przyrost ', tostring(przyrost), ' odbiorcow bez pradu w jednym oknie, lacznie ', tostring(odbiorcy), ' w ', tostring(gminy), ' gminach, etap kaskady ', tostring(max_etap), '. Koordynacja krajowa RCB i operatora sieci.')
| project alert_rule, alert_severity, alert_ts, alert_key, current_value, threshold_value, spo, message, odbiorcy, poprzednio, przyrost, gminy, max_etap
| order by alert_ts asc
}
'@ -split '---NEXT---'

Write-Step "Workspace: $WorkspaceName"
$ResolvedWorkspaceId = Resolve-Workspace
Write-Ok "workspace id = $ResolvedWorkspaceId"

Write-Step 'Activator'
$Activator = Get-OrCreateActivator -workspaceId $ResolvedWorkspaceId
Write-Info "element Reflex: $($Activator.id)"

Write-Step 'Funkcje KQL alertow'
foreach ($command in $FunctionCommands) {
    Invoke-KustoMgmt $command.Trim()
}
Write-Ok "utworzono/zaktualizowano $($FunctionCommands.Count) funkcji"

Write-Step 'Weryfikacja trafien'
$functions = @(
    'alert_izz_critical',
    'alert_care_facility_autonomy',
    'alert_priority_person_nocontact',
    'alert_severe_cold_nopower',
    'alert_heating_point_full',
    'alert_telecom_blackout',
    'alert_delivery_low',
    'alert_cascade_detected'
)
foreach ($functionName in $functions) {
    $metrics = Invoke-KustoQuery "$functionName() | summarize trafienia=count(), klucze=dcount(alert_key), krytyczne=countif(alert_severity == 'critical')"
    $sample = Invoke-KustoQuery "$functionName() | top 1 by current_value desc | project message"
    Write-Host "`n$functionName" -ForegroundColor Yellow
    Write-Host "  liczby : $($metrics.Rows[0] | ConvertTo-Json -Compress)"
    Write-Host "  przyklad: $($sample.Rows[0] | ConvertTo-Json -Compress)"
}

Write-Ok 'Gotowe. Reguly KQL dzialaja; powiadomienia Activator dokoncz w UI wg activator\RULES.md.'
