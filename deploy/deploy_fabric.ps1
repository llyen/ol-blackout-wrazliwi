<#
.SYNOPSIS
    Wdrozenie demo "Tarcza Zimowa - blackout i ludnosc wrazliwa" do Microsoft Fabric.

.DESCRIPTION
    Tworzy i konfiguruje elementy Fabric potrzebne do uruchomienia demo:
      - Lakehouse (wymiary, rejestry i wyniki analiz)
      - Eventhouse / baza KQL (strumienie telemetrii)
      - tabele, mapowania JSON i funkcje pomocnicze w bazie KQL
      - wgranie plikow danych do OneLake
      - zaladowanie strumieni JSONL i wymiarow do Eventhouse

    Uwierzytelnienie: Azure CLI (`az login`). Skrypt pobiera tokeny dla
    api.fabric.microsoft.com (Fabric REST), storage.azure.com (OneLake)
    oraz kusto.kusto.windows.net (Eventhouse).

.PARAMETER Step
    Ktory etap wykonac: all | items | kql | upload | ingest | verify

.EXAMPLE
    .\deploy\deploy_fabric.ps1 -WorkspaceName OL-ZK-Demo-Blackout -CapacityName fcdemo
#>
[CmdletBinding()]
param(
    [string]$WorkspaceName = 'OL-ZK-Demo-Blackout',
    [string]$CapacityName  = '',
    [ValidateSet('all', 'items', 'kql', 'upload', 'ingest', 'verify')]
    [string]$Step = 'all'
)

$ErrorActionPreference = 'Stop'
$RepoRoot       = Split-Path -Parent $PSScriptRoot
$LakehouseName  = 'OL_BLK_Lakehouse'
$EventhouseName = 'OL_BLK_Eventhouse'
$FabricApi      = 'https://api.fabric.microsoft.com/v1'

function Write-Step($msg) { Write-Host "`n=== $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "  $msg" -ForegroundColor Gray }
function Write-Warn($msg) { Write-Host "  [UWAGA] $msg" -ForegroundColor Yellow }

function Get-Token($resource) {
    az account get-access-token --resource $resource --query accessToken -o tsv
}

function Get-FabricHeaders {
    @{ Authorization = "Bearer $(Get-Token 'https://api.fabric.microsoft.com')"; 'Content-Type' = 'application/json' }
}

function Resolve-Workspace {
    $h = Get-FabricHeaders
    $ws = (Invoke-RestMethod -Uri "$FabricApi/workspaces" -Headers $h).value |
          Where-Object displayName -eq $WorkspaceName | Select-Object -First 1
    if ($ws) { return $ws }

    if (-not $CapacityName) { throw "Workspace '$WorkspaceName' nie istnieje. Podaj -CapacityName, aby go utworzyc." }
    $cap = (Invoke-RestMethod -Uri "$FabricApi/capacities" -Headers $h).value |
           Where-Object displayName -eq $CapacityName | Select-Object -First 1
    if (-not $cap) { throw "Nie znaleziono pojemnosci '$CapacityName'." }

    $body = @{ displayName = $WorkspaceName; capacityId = $cap.id } | ConvertTo-Json
    Invoke-RestMethod -Uri "$FabricApi/workspaces" -Headers $h -Method Post -Body $body
}

function New-FabricItem($workspaceId, $type, $name) {
    $h = Get-FabricHeaders
    $existing = (Invoke-RestMethod -Uri "$FabricApi/workspaces/$workspaceId/items" -Headers $h).value |
                Where-Object { $_.displayName -eq $name -and $_.type -eq $type } | Select-Object -First 1
    if ($existing) { Write-Info "$type '$name' juz istnieje"; return $existing }

    $body = @{ displayName = $name; type = $type } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$FabricApi/workspaces/$workspaceId/items" -Headers $h -Method Post -Body $body
    if ($r.StatusCode -eq 202) {
        $op = $r.Headers.Location | Select-Object -First 1
        do {
            Start-Sleep 5
            $st = Invoke-RestMethod -Uri $op -Headers (Get-FabricHeaders)
        } while ($st.status -in 'Running', 'NotStarted')
    }
    $created = (Invoke-RestMethod -Uri "$FabricApi/workspaces/$workspaceId/items" -Headers (Get-FabricHeaders)).value |
               Where-Object { $_.displayName -eq $name -and $_.type -eq $type } | Select-Object -First 1
    Write-Ok "utworzono $type '$name'"
    return $created
}

function Invoke-KustoMgmt($clusterUri, $database, $command) {
    $h = @{ Authorization = "Bearer $(Get-Token 'https://kusto.kusto.windows.net')"; 'Content-Type' = 'application/json' }
    $body = @{ db = $database; csl = $command } | ConvertTo-Json -Depth 3
    Invoke-RestMethod -Uri "$clusterUri/v1/rest/mgmt" -Headers $h -Method Post -Body $body
}

function Invoke-KustoQuery($clusterUri, $database, $query) {
    $h = @{ Authorization = "Bearer $(Get-Token 'https://kusto.kusto.windows.net')"; 'Content-Type' = 'application/json' }
    $body = @{ db = $database; csl = $query } | ConvertTo-Json -Depth 3
    Invoke-RestMethod -Uri "$clusterUri/v1/rest/query" -Headers $h -Method Post -Body $body
}

# Dzieli plik .kql na pojedyncze komendy sterujace (kazda zaczyna sie od kropki).
# Komendy .create-or-alter function maja ciało w nawiasach klamrowych, wiec licznik
# nawiasow decyduje o tym, czy kolejna kropka jest nowa komenda, czy trescia funkcji.
function Split-KqlCommands($path) {
    $commands = @()
    $current = ''
    $depth = 0
    foreach ($line in (Get-Content $path -Encoding UTF8)) {
        if ($line -match '^\s*//' -or $line.Trim() -eq '') { continue }
        if ($line -match '^\s*\.' -and $current.Trim() -and $depth -le 0) { $commands += $current; $current = $line }
        else { if ($current) { $current += "`n$line" } else { $current = $line } }
        $depth += ([regex]::Matches($line, '\{')).Count - ([regex]::Matches($line, '\}')).Count
    }
    if ($current.Trim()) { $commands += $current }
    return $commands
}

function Send-ToOneLake($workspaceId, $lakehouseId, $localPath, $relativePath) {
    $token = Get-Token 'https://storage.azure.com'
    $h = @{ Authorization = "Bearer $token"; 'x-ms-version' = '2021-06-08' }
    $url = "https://onelake.dfs.fabric.microsoft.com/$workspaceId/$lakehouseId/Files/$relativePath"

    Invoke-RestMethod -Uri "${url}?resource=file" -Headers $h -Method Put | Out-Null

    # Duze pliki wysylamy porcjami - pojedynczy append ma limit po stronie uslugi.
    # telecom_coverage.jsonl ma ok. 76 MB, wiec bez dzielenia wysylka by sie nie powiodla.
    $chunkSize = 8MB
    $stream = [System.IO.File]::OpenRead($localPath)
    try {
        $buffer = New-Object byte[] $chunkSize
        $position = 0L
        $hAppend = $h.Clone(); $hAppend['Content-Type'] = 'application/octet-stream'
        while (($read = $stream.Read($buffer, 0, $chunkSize)) -gt 0) {
            $chunk = New-Object byte[] $read
            [Array]::Copy($buffer, 0, $chunk, 0, $read)
            Invoke-RestMethod -Uri "${url}?action=append&position=$position" -Headers $hAppend -Method Patch -Body $chunk | Out-Null
            $position += $read
        }
        Invoke-RestMethod -Uri "${url}?action=flush&position=$position" -Headers $h -Method Patch | Out-Null
    } finally { $stream.Dispose() }
    Write-Ok "$relativePath ($([math]::Round($position / 1MB, 1)) MB)"
}

# =========================================================================
Write-Step "Workspace: $WorkspaceName"
$ws = Resolve-Workspace
Write-Ok "workspace id = $($ws.id)"

Write-Step 'Elementy workspace'
$lakehouse  = New-FabricItem $ws.id 'Lakehouse'  $LakehouseName
$eventhouse = New-FabricItem $ws.id 'Eventhouse' $EventhouseName

$h = Get-FabricHeaders
$ehDetail   = Invoke-RestMethod -Uri "$FabricApi/workspaces/$($ws.id)/eventhouses/$($eventhouse.id)" -Headers $h
$clusterUri = $ehDetail.properties.queryServiceUri
$kqlDbName  = ((Invoke-RestMethod -Uri "$FabricApi/workspaces/$($ws.id)/kqlDatabases" -Headers $h).value |
               Where-Object id -eq $ehDetail.properties.databasesItemIds[0]).displayName
Write-Info "cluster  = $clusterUri"
Write-Info "baza KQL = $kqlDbName"

if ($Step -in 'all', 'upload') {
    Write-Step 'Wgrywanie plikow do OneLake'
    Get-ChildItem "$RepoRoot\datasets" -Filter *.csv | ForEach-Object {
        Send-ToOneLake $ws.id $lakehouse.id $_.FullName "datasets/$($_.Name)"
    }
    Get-ChildItem "$RepoRoot\datasets" -Filter *.jsonl | ForEach-Object {
        Send-ToOneLake $ws.id $lakehouse.id $_.FullName "streams/$($_.Name)"
    }
}

if ($Step -in 'all', 'kql') {
    Write-Step 'Tabele, mapowania i funkcje w Eventhouse'
    # 02_update_policies.kql musi byc wykonany po 01, bo funkcje odwoluja sie do tabel.
    foreach ($file in @('01_create_tables.kql', '02_update_policies.kql')) {
        $path = Join-Path $RepoRoot "kql\$file"
        if (-not (Test-Path $path)) { continue }
        foreach ($cmd in Split-KqlCommands $path) {
            $head = $cmd.Split("`n")[0]
            $head = $head.Substring(0, [Math]::Min(85, $head.Length))
            try { Invoke-KustoMgmt $clusterUri $kqlDbName $cmd | Out-Null; Write-Ok $head }
            catch { Write-Warn "$head :: $($_.Exception.Message)" }
        }
    }
}

if ($Step -in 'all', 'ingest') {
    Write-Step 'Ladowanie strumieni do Eventhouse'
    # klucz = tabela KQL, wartosc = plik JSONL i referencja mapowania
    $map = [ordered]@{
        'WeatherReadings'    = @{ file = 'weather_readings';     mapping = 'weather_readings_mapping' }
        'OutageEvents'       = @{ file = 'outage_events';        mapping = 'outage_events_mapping' }
        'TelecomCoverage'    = @{ file = 'telecom_coverage';     mapping = 'telecom_coverage_mapping' }
        'EmergencyCalls'     = @{ file = 'emergency_calls';      mapping = 'emergency_calls_mapping' }
        'HeatingPointStatus' = @{ file = 'heating_point_status'; mapping = 'heating_point_status_mapping' }
        'GeneratorDispatch'  = @{ file = 'generator_dispatch';   mapping = 'generator_dispatch_mapping' }
        'WelfareCheck'       = @{ file = 'welfare_check';        mapping = 'welfare_check_mapping' }
        'AlertDelivery'      = @{ file = 'alert_delivery';       mapping = 'alert_delivery_mapping' }
    }
    foreach ($table in $map.Keys) {
        $url = "https://onelake.dfs.fabric.microsoft.com/$($ws.id)/$($lakehouse.id)/Files/streams/$($map[$table].file).jsonl"
        try {
            Invoke-KustoMgmt $clusterUri $kqlDbName ".clear table $table data" | Out-Null
            $cmd = ".ingest into table $table ('$url;impersonate') with (format='multijson', ingestionMappingReference='$($map[$table].mapping)')"
            Invoke-KustoMgmt $clusterUri $kqlDbName $cmd | Out-Null
            Write-Ok "zaladowano $table"
        }
        catch { Write-Warn "$table :: $($_.Exception.Message)" }
    }

    # Wymiary musza byc rowniez w Eventhouse: kafelki dashboardu (mapa, etykiety gmin)
    # i funkcje alertowe nie moga siegac do tabel Delta w Lakehouse.
    # CareFacilities ma nazwe inna niz plik, bo tak nazywa ja funkcja
    # CareFacilityAutonomyState w kql/02_update_policies.kql.
    Write-Step 'Ladowanie wymiarow i rejestrow do Eventhouse'
    $dims = [ordered]@{
        'dim_voivodeship' = @{ file = 'dim_voivodeship'; schema = 'voivodeship_code:string, voivodeship_name:string, lat:real, lon:real, scenario_axis:string' }
        'dim_powiat'      = @{ file = 'dim_powiat';      schema = 'powiat_code:string, voivodeship_code:string, powiat_name:string, lat:real, lon:real' }
        'dim_gmina'       = @{ file = 'dim_gmina';       schema = 'gmina_code:string, powiat_code:string, voivodeship_code:string, gmina_name:string, gmina_type:string, population:long, population_density:real, lat:real, lon:real, rurality_index:int' }
        'CareFacilities'  = @{ file = 'dim_care_facility'; schema = 'facility_id:string, facility_type:string, facility_name:string, gmina_code:string, capacity:int, current_occupancy:int, has_generator:bool, generator_autonomy_hours:real, power_need_kw:real, lat:real, lon:real, sensitivity_label:string' }
        'HeatingPoints'   = @{ file = 'dim_heating_point'; schema = 'heating_point_id:string, heating_point_type:string, gmina_code:string, capacity:int, has_generator:bool, has_independent_stove:bool, availability_status:string, power_need_kw:real, lat:real, lon:real' }
        'GeneratorStock'  = @{ file = 'dim_generator_stock'; schema = 'generator_id:string, warehouse_id:string, voivodeship_code:string, power_kw:real, fuel_type:string, mobility_type:string, status:string, lat:real, lon:real' }
        'GridAssets'      = @{ file = 'dim_grid_asset'; schema = 'grid_asset_id:string, asset_type:string, operator_region:string, primary_gmina_code:string, served_gminas:string, customers_served:long, lat:real, lon:real, icing_susceptibility:real' }
        'PopulationVulnerability' = @{ file = 'fact_population_vulnerability'; schema = 'gmina_code:string, population:long, share_75_plus:real, single_senior_households:real, home_oxygen_patients:int, dialysis_patients:int, disability_share:real, care_facility_pressure:real, children_facilities:int, electric_heating_pct:real, no_alt_heat_buildings_pct:real, energy_poverty_pct:real, remote_rurality:int, telecom_gap_pct:real, rescue_travel_time_min:real, vulnerable_population_est:long' }
        'PriorityPersons' = @{ file = 'fact_priority_persons'; schema = 'person_token:string, category:string, gmina_code:string, age_band:string, medical_device_autonomy_hours:real, fictional_contact:string, is_living_alone:bool, sensitivity_label:string, privacy_note:string' }
    }
    foreach ($table in $dims.Keys) {
        $url = "https://onelake.dfs.fabric.microsoft.com/$($ws.id)/$($lakehouse.id)/Files/datasets/$($dims[$table].file).csv"
        try {
            Invoke-KustoMgmt $clusterUri $kqlDbName ".create-merge table $table ($($dims[$table].schema))" | Out-Null
            Invoke-KustoMgmt $clusterUri $kqlDbName ".clear table $table data" | Out-Null
            Invoke-KustoMgmt $clusterUri $kqlDbName ".ingest into table $table ('$url;impersonate') with (format='csv', ignoreFirstRecord=true)" | Out-Null
            Write-Ok "zaladowano $table"
        }
        catch { Write-Warn "$table :: $($_.Exception.Message)" }
    }
}

if ($Step -in 'all', 'verify') {
    Write-Step 'Weryfikacja'
    $q = 'union withsource=T * | summarize Rekordy = count() by Tabela = T | order by Tabela asc'
    $res  = Invoke-KustoQuery $clusterUri $kqlDbName $q
    $cols = $res.Tables[0].Columns.ColumnName
    $res.Tables[0].Rows | ForEach-Object {
        $row = $_; $o = [ordered]@{}
        for ($i = 0; $i -lt $cols.Count; $i++) { $o[$cols[$i]] = $row[$i] }
        [PSCustomObject]$o
    } | Format-Table -AutoSize
}

Write-Host "`nGotowe. Workspace: https://app.fabric.microsoft.com/groups/$($ws.id)" -ForegroundColor Cyan
