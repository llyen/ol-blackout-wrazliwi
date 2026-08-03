<#
.SYNOPSIS
    Tworzy albo aktualizuje Real-Time Dashboard scenariusza „Tarcza Zimowa" w Microsoft Fabric.

.DESCRIPTION
    Skrypt czyta zapytania z kql\03_dashboard_queries.kql, waliduje je przez
    Eventhouse REST API, buduje definicję RealTimeDashboard.json i zapisuje ją
    lokalnie w dashboard\. Następnie tworzy element KQLDashboard albo nadpisuje
    definicję istniejącego elementu OL_BLK_Dashboard.

.EXAMPLE
    .\deploy\create_dashboard.ps1 -WorkspaceName OL-ZK-Demo-Blackout
#>
[CmdletBinding()]
param(
    [string]$WorkspaceName = 'OL-ZK-Demo-Blackout',
    [string]$DashboardName = 'OL_BLK_Dashboard',
    [string]$WorkspaceId = '68e1369e-bc4d-4c87-a747-e3fd78c21f21',
    [string]$ClusterUri = 'https://trd-bv9kuej96btp7bpuq7.z6.kusto.fabric.microsoft.com',
    [string]$KqlDatabaseName = 'OL_BLK_Eventhouse',
    [string]$KqlDatabaseId = '2b228a24-f180-4b27-a916-688208854533',
    [switch]$SkipQueryValidation
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$FabricApi = 'https://api.fabric.microsoft.com/v1'
$QueriesPath = Join-Path $RepoRoot 'kql\03_dashboard_queries.kql'
$DashboardJsonPath = Join-Path $RepoRoot 'dashboard\RealTimeDashboard.json'

function Write-Step($msg) { Write-Host "`n=== $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "  $msg" -ForegroundColor Gray }
function Write-Warn($msg) { Write-Host "  [UWAGA] $msg" -ForegroundColor Yellow }

function Get-Token($resource) {
    az account get-access-token --resource $resource --query accessToken -o tsv
}

function Get-FabricHeaders {
    @{ Authorization = "Bearer $(Get-Token 'https://api.fabric.microsoft.com')"; 'Content-Type' = 'application/json' }
}

function Resolve-Workspace {
    $workspaces = (Invoke-RestMethod -Uri "$FabricApi/workspaces" -Headers (Get-FabricHeaders)).value
    $ws = $workspaces | Where-Object displayName -eq $WorkspaceName | Select-Object -First 1
    if (-not $ws) {
        if ($WorkspaceId) { Write-Warn "Nie znaleziono workspace '$WorkspaceName'; używam podanego id $WorkspaceId."; return }
        throw "Nie znaleziono workspace '$WorkspaceName'."
    }
    $script:WorkspaceId = $ws.id
    Write-Info "workspace: $($ws.displayName) ($WorkspaceId)"
}

function Get-KustoHeaders {
    @{ Authorization = "Bearer $(Get-Token 'https://kusto.kusto.windows.net')"; 'Content-Type' = 'application/json' }
}

function New-StableGuid([string]$value) {
    $bytes = [Text.Encoding]::UTF8.GetBytes("ol-blk-dashboard-$value")
    $hash = [Security.Cryptography.MD5]::Create().ComputeHash($bytes)
    return ([Guid]::new($hash)).ToString()
}

function Split-DashboardQueries([string]$path) {
    $text = Get-Content $path -Raw -Encoding UTF8
    $pattern = '(?ms)^//\s*(\d{2})\.\s*Kafelek:\s*„([^”]+)”\s*\|\s*Strona:\s*(.+?)\r?\n(.*?)(?=^//\s*\d{2}\.\s*Kafelek:|\z)'
    $matches = [regex]::Matches($text, $pattern)
    foreach ($m in $matches) {
        $block = $m.Groups[4].Value
        $query = ($block -split "`r?`n" | Where-Object { $_ -notmatch '^\s*//' -and $_.Trim() -ne '' }) -join "`n"
        [PSCustomObject]@{
            Number = $m.Groups[1].Value
            Title  = $m.Groups[2].Value
            Page   = $m.Groups[3].Value.Trim()
            Query  = $query.Trim()
        }
    }
}

function Invoke-KustoQuery([string]$query) {
    $body = @{ db = $KqlDatabaseName; csl = $query } | ConvertTo-Json -Depth 8
    Invoke-RestMethod -Uri "$ClusterUri/v1/rest/query" -Headers (Get-KustoHeaders) -Method Post -Body $body
}

function Wait-FabricOperation([string]$operationUrl) {
    if (-not $operationUrl) { return $null }
    do {
        Start-Sleep 5
        $state = Invoke-RestMethod -Uri $operationUrl -Headers (Get-FabricHeaders)
        Write-Info "operacja Fabric: $($state.status)"
    } while ($state.status -in 'NotStarted', 'Running')

    if ($state.status -notin 'Succeeded', 'Completed') {
        $details = $state | ConvertTo-Json -Depth 20
        throw "Operacja Fabric nie powiodła się: $details"
    }
    return $state
}

function Invoke-FabricRequest([string]$Method, [string]$Uri, $Body = $null) {
    $json = if ($null -ne $Body) { $Body | ConvertTo-Json -Depth 100 } else { $null }
    try {
        $r = Invoke-WebRequest -Uri $Uri -Headers (Get-FabricHeaders) -Method $Method -Body $json
        if ($r.StatusCode -eq 202) {
            $op = $r.Headers.Location | Select-Object -First 1
            Wait-FabricOperation $op | Out-Null
        }
        return $r
    } catch {
        if ($_.ErrorDetails.Message) { Write-Warn $_.ErrorDetails.Message }
        $op = $_.Exception.Response.Headers.Location | Select-Object -First 1
        if ($op) { Wait-FabricOperation $op | Out-Null }
        throw
    }
}

function Get-PrimaryPage([string]$headerPage) {
    $known = @('Obraz sytuacji', 'Ludnosc wrazliwa', 'Cieplo i opieka', 'Lacznosc i ostrzeganie', 'Pogoda i prognoza')
    foreach ($page in $known) {
        if ($headerPage -like "*$page*") { return $page }
    }
    return 'Obraz sytuacji'
}

function Get-UsedVariables([string]$queryText) {
    # Dashboard wiaze parametry z zapytaniem tylko wtedy, gdy zmienne sa tu wymienione.
    @('_startTime', '_endTime') | Where-Object { $queryText -match [regex]::Escape($_) }
}

function Get-VisualType([string]$number) {
    switch ($number) {
        { $_ -in @('01', '11', '16', '20') } { 'map'; break }
        '02' { 'multistat'; break }
        '08' { 'pie'; break }
        { $_ -in @('04', '07', '12', '14', '18') } { 'column'; break }
        { $_ -in @('03', '09', '15', '17', '21') } { 'line'; break }
        default { 'table' }
    }
}

function Get-VisualOptions([string]$number, [string]$visualType) {
    if ($visualType -eq 'table') {
        return @{
            table__enableRenderLinks = $true
            colorRulesDisabled = $true
            colorStyle = 'light'
            crossFilterDisabled = $false
            drillthroughDisabled = $false
            crossFilter = @()
            drillthrough = @()
            table__renderLinks = @()
            colorRules = @()
        }
    }
    if ($visualType -eq 'multistat') {
        return @{
            multiStat__textSize = 'auto'
            multiStat__displayOrientation = 'horizontal'
            multiStat__valueColumn = 'Wartosc'
            multiStat__labelColumn = 'Wskaznik'
            colorRulesDisabled = $true
            colorStyle = 'light'
            multiStat__slot = @{ width = 4; height = 1 }
            colorRules = @()
        }
    }
    # Schemat kafelka (schema/60/tile.json) dopuszcza wylacznie te cztery wlasciwosci mapy.
    # Nieznane klucze (map__geoType, map__sizeColumn) powodowaly, ze kontrolka ignorowala
    # kolumny lat/lon i probowala geokodowac po nazwie - stad wielosekundowe ladowanie.
    if ($visualType -eq 'map') {
        $sizeColumn = switch ($number) { '01' { 'Odbiorcy' } '11' { 'Osoby' } '16' { 'BTSnaBaterii' } '20' { 'Wiatr' } default { 'Waga' } }
        return @{
            map__bubbleFormat = 'bubble'
            map__latitudeColumn = 'lat'
            map__longitudeColumn = 'lon'
            map__minBubbleSizeColumn = $sizeColumn
            hideLegend = $false
            legendLocation = 'bottom'
        }
    }
    if ($visualType -eq 'heatmap') {
        return @{
            xColumn = 'Doba'
            yColumn = 'Wojewodztwo'
            heatMap__dataColumn = 'Zgloszenia'
            heatMap__colorPaletteKey = 'orange'
            colorRulesDisabled = $true
            colorRules = @()
        }
    }
    if ($visualType -eq 'pie') {
        return @{
            xColumn = 'Kategoria'
            yColumns = @('Osoby')
            pie__kind = 'donut'
            pie__label = @('name', 'percentage')
            pie__orderBy = 'size'
            hideLegend = $false
            legendLocation = 'right'
        }
    }

    $axis = switch ($number) {
        '03' { @{ xColumn = 'Czas'; yColumns = @('Odbiorcy'); seriesColumns = @('Etap'); xColumnTitle = 'Czas' } }
        '04' { @{ xColumn = 'Wojewodztwo'; yColumns = @('Odbiorcy'); seriesColumns = $null; xColumnTitle = 'Wojewodztwo' } }
        '07' { @{ xColumn = 'Wojewodztwo'; yColumns = @('Wrazliwi'); seriesColumns = $null; xColumnTitle = 'Wojewodztwo' } }
        '09' { @{ xColumn = 'Czas'; yColumns = @('Zgloszenia'); seriesColumns = @('Rodzaj'); xColumnTitle = 'Czas' } }
        '12' { @{ xColumn = 'Punkt'; yColumns = @('Zapelnienie'); seriesColumns = $null; xColumnTitle = 'Punkt grzewczy' } }
        '14' { @{ xColumn = 'Stan'; yColumns = @('Agregaty'); seriesColumns = @('Cel'); xColumnTitle = 'Stan dysponowania' } }
        '15' { @{ xColumn = 'Czas'; yColumns = @('MocKW', 'Dyspozycje'); seriesColumns = $null; xColumnTitle = 'Czas' } }
        '17' { @{ xColumn = 'Czas'; yColumns = @('SrednePokrycie', 'GminyPonizej20', 'GminyPonizej60'); seriesColumns = $null; xColumnTitle = 'Czas' } }
        '18' { @{ xColumn = 'Kanal'; yColumns = @('Dostarczalnosc'); seriesColumns = $null; xColumnTitle = 'Kanal ostrzegania' } }
        '21' { @{ xColumn = 'Czas'; yColumns = @('Odczuwalna', 'Temperatura', 'Wiatr'); seriesColumns = $null; xColumnTitle = 'Czas' } }
        default { @{ xColumn = $null; yColumns = @(); seriesColumns = $null; xColumnTitle = '' } }
    }

    return @{
        multipleYAxes = @{
            base = @{
                id = '-1'
                label = ''
                columns = @()
                yAxisMaximumValue = $null
                yAxisMinimumValue = $null
                yAxisScale = 'linear'
                horizontalLines = @()
            }
            additional = @()
            showMultiplePanels = $false
        }
        hideLegend = $false
        legendLocation = 'bottom'
        xColumnTitle = $axis.xColumnTitle
        xColumn = $axis.xColumn
        yColumns = $axis.yColumns
        seriesColumns = $axis.seriesColumns
        xAxisScale = 'linear'
        verticalLine = ''
        crossFilterDisabled = $false
        drillthroughDisabled = $false
        crossFilter = @()
        drillthrough = @()
    }
}

function New-DashboardJson($queries, [string]$schemaVersion, [switch]$Minimal) {
    $pageNames = @('Obraz sytuacji', 'Ludnosc wrazliwa', 'Cieplo i opieka', 'Lacznosc i ostrzeganie', 'Pogoda i prognoza')
    $pages = foreach ($p in $pageNames) { [ordered]@{ name = $p; id = New-StableGuid "page-$p" } }
    $pageIdByName = @{}
    foreach ($p in $pages) { $pageIdByName[$p.name] = $p.id }
    $dataSourceId = New-StableGuid 'datasource-eventhouse'
    $selected = if ($Minimal) { @($queries | Select-Object -First 1) } else { @($queries) }

    $tiles = @()
    $queryDefs = @()
    $positions = @{}
    foreach ($p in $pageNames) { $positions[$p] = 0 }

    foreach ($q in $selected) {
        $pageName = Get-PrimaryPage $q.Page
        $index = [int]$positions[$pageName]
        $positions[$pageName] = $index + 1
        $visualType = Get-VisualType $q.Number
        $queryId = New-StableGuid "query-$($q.Number)"

        $width = if ($visualType -in @('multistat', 'bar', 'pie')) { 6 } elseif ($visualType -eq 'stat') { 4 } else { 12 }
        $height = if ($visualType -in @('multistat', 'stat')) { 3 } elseif ($visualType -eq 'table') { 7 } else { 8 }
        $tile = [ordered]@{
            id = New-StableGuid "tile-$($q.Number)"
            title = $q.Title
            visualType = $visualType
            pageId = $pageIdByName[$pageName]
            layout = [ordered]@{
                x = ($index % 2) * 12
                y = [int]([math]::Floor($index / 2) * 8)
                width = $width
                height = $height
            }
            queryRef = [ordered]@{ kind = 'query'; queryId = $queryId }
            visualOptions = Get-VisualOptions $q.Number $visualType
        }
        $tiles += $tile
        $queryDefs += [ordered]@{
            dataSource = [ordered]@{ kind = 'inline'; dataSourceId = $dataSourceId }
            text = $q.Query
            id = $queryId
            usedVariables = @(Get-UsedVariables $q.Query)
        }
    }

    [ordered]@{
        '$schema' = "https://pbiadx.powerbi.com/static/d/schema/$schemaVersion/dashboard.json"
        id = New-StableGuid 'dashboard'
        eTag = ''
        schema_version = $schemaVersion
        title = $DashboardName
        autoRefresh = [ordered]@{ enabled = $true; defaultInterval = '10s'; minInterval = '10s' }
        tiles = $tiles
        baseQueries = @()
        parameters = @(
            [ordered]@{
                kind = 'duration'
                id = New-StableGuid 'parameter-time-range'
                displayName = 'Zakres czasu'
                description = 'Ruchome okno ostatnich 15 minut zegara. Scenariusz biegnie w tempie 60x, wiec okno obejmuje ok. 15 godzin akcji i przesuwa sie razem z zegarem.'
                beginVariableName = '_startTime'
                endVariableName = '_endTime'
                # Okno musi byc wyraznie krotsze niz jeden cykl odtwarzania (24 min przy
                # tempie 60x). Przy oknie dluzszym od cyklu w kadrze lezy cala scena naraz,
                # przyrost gina w masie i dashboard wyglada na zamrozony.
                defaultValue = [ordered]@{ kind = 'dynamic'; count = 15; unit = 'minutes' }
                showOnPages = [ordered]@{ kind = 'all' }
            }
        )
        dataSources = @(
            [ordered]@{
                kind = 'kusto-trident'
                scopeId = 'kusto-trident'
                clusterUri = $ClusterUri
                database = $KqlDatabaseId
                name = $KqlDatabaseName
                id = $dataSourceId
                workspace = $WorkspaceId
            }
        )
        pages = $pages
        queries = $queryDefs
    }
}

function New-Definition($dashboardObject) {
    $json = $dashboardObject | ConvertTo-Json -Depth 100
    [IO.File]::WriteAllText($DashboardJsonPath, $json, [Text.UTF8Encoding]::new($false))
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
    @{
        format = $null
        parts = @(
            @{
                path = 'RealTimeDashboard.json'
                payload = $payload
                payloadType = 'InlineBase64'
            }
        )
    }
}

function Get-DashboardItem {
    $items = (Invoke-RestMethod -Uri "$FabricApi/workspaces/$WorkspaceId/kqlDashboards" -Headers (Get-FabricHeaders)).value
    $items | Where-Object displayName -eq $DashboardName | Select-Object -First 1
}

Write-Step "Workspace"
Resolve-Workspace

Write-Step "Czytanie zapytań"
$dashboardQueries = @(Split-DashboardQueries $QueriesPath)
if ($dashboardQueries.Count -ne 22) { throw "Oczekiwano 22 zapytań, znaleziono $($dashboardQueries.Count)." }
Write-Ok "znaleziono $($dashboardQueries.Count) zapytań"

if (-not $SkipQueryValidation) {
    Write-Step "Walidacja KQL przez Eventhouse REST"
    foreach ($q in $dashboardQueries) {
        # Zapytania kafelkow filtruja po zmiennych dashboardu, ktorych Eventhouse nie zna.
        # Na czas walidacji podstawiamy je tak samo, jak robi to dashboard: ostatnie 15 minut.
        $toRun = if (Get-UsedVariables $q.Query) {
            "let _startTime = ago(15m);`nlet _endTime = now();`n$($q.Query)"
        } else { $q.Query }
        $res = Invoke-KustoQuery $toRun
        $rows = if ($res.Tables -and $res.Tables.Count -gt 0) { $res.Tables[0].Rows.Count } else { 0 }
        Write-Ok "$($q.Number). $($q.Title) ($rows wierszy)"
    }
}

Write-Step "Publikacja dashboardu"
$attempts = @(
    @{ Schema = '60'; Minimal = $false },
    @{ Schema = '52'; Minimal = $false },
    @{ Schema = '60'; Minimal = $true },
    @{ Schema = '52'; Minimal = $true },
    @{ Schema = '48'; Minimal = $true },
    @{ Schema = '48'; Minimal = $false }
)

$existing = Get-DashboardItem
$success = $false
$lastError = $null
foreach ($attempt in $attempts) {
    try {
        $dashboardObject = New-DashboardJson $dashboardQueries $attempt.Schema -Minimal:([bool]$attempt.Minimal)
        $definition = New-Definition $dashboardObject
        $mode = if ($attempt.Minimal) { 'minimalna' } else { 'pełna' }
        Write-Info "próba: schema_version=$($attempt.Schema), definicja=$mode"

        if ($existing) {
            Invoke-FabricRequest -Method Post -Uri "$FabricApi/workspaces/$WorkspaceId/kqlDashboards/$($existing.id)/updateDefinition" -Body @{ definition = $definition } | Out-Null
            Write-Ok "zaktualizowano KQLDashboard $DashboardName ($($existing.id))"
        } else {
            $body = @{
                displayName = $DashboardName
                description = 'Real-Time Dashboard demo: blackout i ludnosc wrazliwa'
                definition = $definition
            }
            Invoke-FabricRequest -Method Post -Uri "$FabricApi/workspaces/$WorkspaceId/kqlDashboards" -Body $body | Out-Null
            $existing = Get-DashboardItem
            Write-Ok "utworzono KQLDashboard $DashboardName ($($existing.id))"
        }
        $success = $true
        break
    } catch {
        $lastError = $_
        Write-Warn "nieudana próba: $($_.Exception.Message)"
    }
}

if (-not $success) {
    Write-Warn "Nie udało się wgrać definicji po 6 próbach. Tworzę pusty dashboard, jeśli go nie ma."
    if (-not $existing) {
        Invoke-FabricRequest -Method Post -Uri "$FabricApi/workspaces/$WorkspaceId/kqlDashboards" -Body @{
            displayName = $DashboardName
            description = 'Real-Time Dashboard demo: Tarcza Zimowa; definicja do importu w dashboard\RealTimeDashboard.json'
        } | Out-Null
        $existing = Get-DashboardItem
    }
    if ($lastError) { Write-Warn $lastError.Exception.Message }
}

Write-Step "Weryfikacja"
$list = (Invoke-RestMethod -Uri "$FabricApi/workspaces/$WorkspaceId/kqlDashboards" -Headers (Get-FabricHeaders)).value
$item = $list | Where-Object displayName -eq $DashboardName | Select-Object -First 1
if (-not $item) { throw "Dashboard $DashboardName nie istnieje po publikacji." }
Write-Ok "dashboard istnieje: $($item.id)"

$defResponse = Invoke-RestMethod -Uri "$FabricApi/workspaces/$WorkspaceId/kqlDashboards/$($item.id)/getDefinition" -Headers (Get-FabricHeaders) -Method Post
$part = $defResponse.definition.parts | Where-Object path -eq 'RealTimeDashboard.json' | Select-Object -First 1
if ($part) {
    $decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($part.payload)) | ConvertFrom-Json
    Write-Ok "definicja zawiera $($decoded.pages.Count) stron i $($decoded.tiles.Count) kafelków"
} else {
    Write-Warn "API nie zwróciło części RealTimeDashboard.json; lokalny plik: $DashboardJsonPath"
}

Write-Host "`nGotowe: https://app.fabric.microsoft.com/groups/$WorkspaceId" -ForegroundColor Cyan
