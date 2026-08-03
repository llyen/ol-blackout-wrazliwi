<#
.SYNOPSIS
    Uruchamia notatnik z katalogu notebooks\fabric i zwraca pelny traceback bledu.

.DESCRIPTION
    Fabric Jobs API zwraca przy niepowodzeniu tylko ogolny komunikat
    "System cancelled the Spark session due to statement execution failures",
    bez tresci wyjatku. Ten skrypt buduje tymczasowy notatnik, ktory wykonuje
    kod docelowego notatnika w bloku try/except i zapisuje traceback do pliku
    w Files/_debug w Lakehouse. Skrypt czeka na zakonczenie zadania, pobiera
    plik z OneLake i wypisuje go na konsole.

    Kod zrodlowy jest przekazywany jako base64, zeby uniknac kolizji cudzyslowow
    i znakow ucieczki przy osadzaniu go w komorce notatnika.

.EXAMPLE
    .\deploy\debug_notebook.ps1 -Notebook 03_dynamic_risk
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Notebook,
    [string]$WorkspaceName = 'OL-ZK-Demo-Blackout',
    [string]$LakehouseName = 'OL_BLK_Lakehouse',
    [int]$TimeoutMinutes   = 20,
    [switch]$KeepNotebook
)

$ErrorActionPreference = 'Stop'
$RepoRoot  = Split-Path -Parent $PSScriptRoot
$FabricApi = 'https://api.fabric.microsoft.com/v1'
$DebugName = "_debug_$Notebook"

function Get-Headers {
    @{ Authorization = "Bearer $(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)"; 'Content-Type' = 'application/json' }
}

$source = Join-Path $RepoRoot "notebooks\fabric\$Notebook.py"
if (-not (Test-Path $source)) { throw "Nie znaleziono $source" }

# Markery komorek nie sa potrzebne - kod wykonujemy jako jeden blok.
$code = (Get-Content $source -Raw -Encoding UTF8) -replace '(?m)^\s*#\s*CELL\s*$', ''
$b64  = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code))

$cellLines = @(
    'import base64, contextlib, io, traceback',
    "code = base64.b64decode('$b64').decode('utf-8')",
    'buf = io.StringIO()',
    'try:',
    '    with contextlib.redirect_stdout(buf):',
    '        exec(compile(code, "notebook", "exec"), globals())',
    '    log = buf.getvalue() + "\n=== OK ==="',
    'except Exception:',
    '    log = buf.getvalue() + "\n=== TRACEBACK ===\n" + traceback.format_exc()',
    "notebookutils.fs.put('Files/_debug/$Notebook.txt', log, True)",
    'print(log)'
)

$h  = Get-Headers
$ws = (Invoke-RestMethod -Uri "$FabricApi/workspaces" -Headers $h).value | Where-Object displayName -eq $WorkspaceName | Select-Object -First 1
if (-not $ws) { throw "Nie znaleziono workspace '$WorkspaceName'." }
$items = (Invoke-RestMethod -Uri "$FabricApi/workspaces/$($ws.id)/items" -Headers $h).value
$lh = $items | Where-Object { $_.type -eq 'Lakehouse' -and $_.displayName -eq $LakehouseName } | Select-Object -First 1
if (-not $lh) { throw "Nie znaleziono Lakehouse '$LakehouseName'." }

$nbJson = [ordered]@{
    nbformat = 4; nbformat_minor = 5
    cells = @(@{ cell_type = 'code'; execution_count = $null; metadata = @{}; outputs = @(); source = @($cellLines | ForEach-Object { "$_`n" }) })
    metadata = [ordered]@{
        language_info = @{ name = 'python' }
        dependencies  = [ordered]@{ lakehouse = [ordered]@{ default_lakehouse = $lh.id; default_lakehouse_name = $lh.displayName; default_lakehouse_workspace_id = $ws.id } }
    }
} | ConvertTo-Json -Depth 20

$definition = @{ format = 'ipynb'; parts = @(@{ path = 'notebook-content.ipynb'; payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($nbJson)); payloadType = 'InlineBase64' }) }
$existing = $items | Where-Object { $_.type -eq 'Notebook' -and $_.displayName -eq $DebugName } | Select-Object -First 1

if ($existing) {
    Invoke-RestMethod -Uri "$FabricApi/workspaces/$($ws.id)/notebooks/$($existing.id)/updateDefinition" -Headers (Get-Headers) -Method Post -Body (@{ definition = $definition } | ConvertTo-Json -Depth 10) | Out-Null
    $nbId = $existing.id
} else {
    $r = Invoke-WebRequest -Uri "$FabricApi/workspaces/$($ws.id)/notebooks" -Headers (Get-Headers) -Method Post -Body (@{ displayName = $DebugName; definition = $definition } | ConvertTo-Json -Depth 10)
    if ($r.StatusCode -eq 202) {
        $op = $r.Headers.Location | Select-Object -First 1
        do { Start-Sleep 5; $st = Invoke-RestMethod -Uri $op -Headers (Get-Headers) } while ($st.status -in 'Running', 'NotStarted')
    }
    $nbId = ((Invoke-RestMethod -Uri "$FabricApi/workspaces/$($ws.id)/notebooks" -Headers (Get-Headers)).value | Where-Object displayName -eq $DebugName).id
}
Write-Host "Notatnik diagnostyczny: $DebugName ($nbId)" -ForegroundColor Cyan

$start = Get-Date
$run = Invoke-WebRequest -Method POST -Headers (Get-Headers) -Uri "$FabricApi/workspaces/$($ws.id)/items/$nbId/jobs/instances?jobType=RunNotebook" -Body '{}'
$location = @($run.Headers.Location) | Select-Object -First 1
do {
    Start-Sleep 10
    $status = (Invoke-RestMethod -Uri $location -Headers (Get-Headers)).status
    Write-Host "  $status ($([int]((Get-Date) - $start).TotalSeconds) s)" -ForegroundColor Gray
    if (((Get-Date) - $start).TotalMinutes -gt $TimeoutMinutes -and $status -in 'NotStarted', 'InProgress', 'Running') { throw 'Przekroczono limit czasu.' }
} while ($status -in 'NotStarted', 'InProgress', 'Running')

$sh = @{ Authorization = "Bearer $(az account get-access-token --resource https://storage.azure.com --query accessToken -o tsv)" }
$url = "https://onelake.dfs.fabric.microsoft.com/$($ws.id)/$($lh.id)/Files/_debug/$Notebook.txt"
try {
    Write-Host "`n--- traceback ---" -ForegroundColor Yellow
    Invoke-RestMethod -Uri $url -Headers $sh
} catch {
    Write-Host "Brak pliku diagnostycznego (status zadania: $status). Sesja Spark mogla paść przed zapisem." -ForegroundColor Yellow
}

if (-not $KeepNotebook) {
    Invoke-RestMethod -Uri "$FabricApi/workspaces/$($ws.id)/items/$nbId" -Headers (Get-Headers) -Method Delete | Out-Null
    Write-Host "`nUsunieto notatnik diagnostyczny." -ForegroundColor Gray
}
