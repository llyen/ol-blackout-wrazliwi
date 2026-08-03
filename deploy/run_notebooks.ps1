<#
.SYNOPSIS
    Uruchamia notatniki przeliczajace warstwe Lakehouse po regeneracji danych.

.DESCRIPTION
    Kolejnosc ma znaczenie: wymiary -> strumienie -> wskaznik wrazliwosci ->
    ryzyko dynamiczne -> dobor punktow grzewczych -> priorytety wizyt -> what-if.
    Kazdy notatnik jest uruchamiany przez Fabric Jobs API i odpytywany az do zakonczenia.

.EXAMPLE
    .\deploy\run_notebooks.ps1
#>
[CmdletBinding()]
param(
    [string]$WorkspaceName = 'OL-ZK-Demo-Blackout',
    [string[]]$Notebooks = @('01_load_dimensions', '01b_load_streams', '02_vulnerability_index', '03_dynamic_risk', '04_heating_point_siting', '05_welfare_check_prioritization', '06_whatif'),
    [int]$TimeoutMinutes = 25
)

$ErrorActionPreference = 'Stop'
$FabricApi = 'https://api.fabric.microsoft.com/v1'

# Lancuch notatnikow trwa dluzej niz zycie tokenu z cache az, dlatego token odswiezamy
# cyklicznie zamiast pobierac raz na starcie - inaczej dlugi przebieg konczy sie
# bledem TokenExpired w polowie pracy.
$script:tokenValue = $null
$script:tokenTaken = [datetime]::MinValue
function Get-Headers {
    if (-not $script:tokenValue -or ((Get-Date) - $script:tokenTaken).TotalMinutes -gt 15) {
        $script:tokenValue = az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv
        if (-not $script:tokenValue) { throw 'Brak tokenu Fabric. Uruchom az login.' }
        $script:tokenTaken = Get-Date
    }
    @{ Authorization = 'Bearer ' + $script:tokenValue; 'Content-Type' = 'application/json' }
}

$ws = (Invoke-RestMethod -Uri "$FabricApi/workspaces" -Headers (Get-Headers)).value |
      Where-Object displayName -eq $WorkspaceName | Select-Object -First 1
if (-not $ws) { throw "Nie znaleziono workspace '$WorkspaceName'." }
$WorkspaceId = $ws.id

$items = (Invoke-RestMethod -Uri "$FabricApi/workspaces/$WorkspaceId/notebooks" -Headers (Get-Headers)).value
$results = [System.Collections.Generic.List[object]]::new()

foreach ($name in $Notebooks) {
    $item = $items | Where-Object displayName -eq $name
    if (-not $item) { throw "Nie znaleziono notatnika '$name' w workspace." }

    Write-Host "=== $name" -ForegroundColor Cyan
    $start = Get-Date
    $run = Invoke-WebRequest -Method POST -Headers (Get-Headers) `
        -Uri "$FabricApi/workspaces/$WorkspaceId/items/$($item.id)/jobs/instances?jobType=RunNotebook" -Body '{}'
    $location = @($run.Headers.Location) | Select-Object -First 1
    if (-not $location) { throw "$name : brak naglowka Location w odpowiedzi." }

    do {
        Start-Sleep -Seconds 10
        $status = (Invoke-RestMethod -Uri $location -Headers (Get-Headers)).status
        $elapsed = [int]((Get-Date) - $start).TotalSeconds
        Write-Host "  $status ($elapsed s)" -ForegroundColor Gray
        # Limit sprawdzamy tylko dla zadania wciaz trwajacego - status koncowy
        # ma pierwszenstwo, bo zegar hosta potrafi przeskoczyc miedzy odpytaniami.
        if ($elapsed -gt $TimeoutMinutes * 60 -and $status -in @('NotStarted', 'InProgress', 'Running')) { throw "$name : przekroczono limit $TimeoutMinutes min." }
    } while ($status -in @('NotStarted', 'InProgress', 'Running'))

    if ($status -ne 'Completed') { throw "$name zakonczyl sie statusem $status." }
    $results.Add([pscustomobject]@{ Notatnik = $name; Status = $status; Sekundy = [int]((Get-Date) - $start).TotalSeconds })
}

$results | Format-Table -AutoSize
