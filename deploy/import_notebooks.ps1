<#
.SYNOPSIS
    Import notebookow scenariusza blackout do workspace Microsoft Fabric.

.DESCRIPTION
    Konwertuje pliki `.py` z komorkami oznaczonymi `# CELL` na format `.ipynb`
    i tworzy (lub aktualizuje) elementy typu Notebook w workspace.
    Kazdy notebook zostaje domyslnie podpiety do wskazanego Lakehouse.

.EXAMPLE
    .\deploy\import_notebooks.ps1 -WorkspaceName OL-ZK-Demo-Blackout
#>
[CmdletBinding()]
param(
    [string]$WorkspaceName  = 'OL-ZK-Demo-Blackout',
    [string]$LakehouseName  = 'OL_BLK_Lakehouse'
)

$ErrorActionPreference = 'Stop'
$RepoRoot  = Split-Path -Parent $PSScriptRoot
$FabricApi = 'https://api.fabric.microsoft.com/v1'

function Get-Token($resource) { az account get-access-token --resource $resource --query accessToken -o tsv }
function Get-Headers { @{ Authorization = "Bearer $(Get-Token 'https://api.fabric.microsoft.com')"; 'Content-Type' = 'application/json' } }

# Format .ipynb wymaga, aby zawartosc komorki byla lista linii zakonczonych znakiem nowej linii.
function ConvertTo-SourceLines($text) {
    $lines = @($text -split "`r?`n" | ForEach-Object { "$_`n" })
    if ($lines.Count) { $lines[-1] = $lines[-1].TrimEnd("`n") }
    # Jednoelementowa tablica zostalaby zserializowana jako wartosc skalarna.
    if ($lines.Count -eq 1) { $lines += '' }
    return , $lines
}

# Zamienia skrypt z markerami "# CELL" na strukture notatnika Jupyter.
function ConvertTo-Notebook($pyPath, $workspaceId, $lakehouseId, $lakehouseName) {
    $cells = @()
    $current = @()
    foreach ($line in (Get-Content $pyPath -Encoding UTF8)) {
        if ($line -match '^\s*#\s*CELL\s*$') {
            if ($current.Count) { $cells += , $current }
            $current = @()
        } else { $current += $line }
    }
    if ($current.Count) { $cells += , $current }

    $nbCells = foreach ($cell in $cells) {
        $text = ($cell -join "`n").Trim()
        if (-not $text) { continue }
        # Komorka zlozona wylacznie z komentarzy staje sie komorka markdown.
        $isComment = ($cell | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_ -match '^\s*#' }) -notcontains $false
        if ($isComment) {
            $text = (($cell | ForEach-Object { $_ -replace '^\s*#\s?', '' }) -join "`n").Trim()
            [ordered]@{ cell_type = 'markdown'; metadata = @{}; source = (ConvertTo-SourceLines $text) }
        } else {
            [ordered]@{ cell_type = 'code'; execution_count = $null; metadata = @{}; outputs = @(); source = (ConvertTo-SourceLines $text) }
        }
    }

    [ordered]@{
        nbformat       = 4
        nbformat_minor = 5
        cells          = @($nbCells)
        metadata       = [ordered]@{
            language_info  = @{ name = 'python' }
            dependencies   = [ordered]@{
                lakehouse = [ordered]@{
                    default_lakehouse      = $lakehouseId
                    default_lakehouse_name = $lakehouseName
                    default_lakehouse_workspace_id = $workspaceId
                }
            }
        }
    }
}

$h  = Get-Headers
$ws = (Invoke-RestMethod -Uri "$FabricApi/workspaces" -Headers $h).value | Where-Object displayName -eq $WorkspaceName | Select-Object -First 1
if (-not $ws) { throw "Nie znaleziono workspace '$WorkspaceName'." }
$items = (Invoke-RestMethod -Uri "$FabricApi/workspaces/$($ws.id)/items" -Headers $h).value
$lh = $items | Where-Object { $_.type -eq 'Lakehouse' -and $_.displayName -eq $LakehouseName } | Select-Object -First 1
if (-not $lh) { throw "Nie znaleziono Lakehouse '$LakehouseName'." }

Write-Host "Workspace: $($ws.displayName) ($($ws.id))" -ForegroundColor Cyan

foreach ($py in Get-ChildItem "$RepoRoot\notebooks\fabric" -Filter *.py | Sort-Object Name) {
    $name = $py.BaseName
    $nb   = ConvertTo-Notebook $py.FullName $ws.id $lh.id $lh.displayName
    $json = $nb | ConvertTo-Json -Depth 20
    $b64  = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))

    $definition = @{
        format = 'ipynb'
        parts  = @(@{ path = 'notebook-content.ipynb'; payload = $b64; payloadType = 'InlineBase64' })
    }

    $existing = $items | Where-Object { $_.type -eq 'Notebook' -and $_.displayName -eq $name } | Select-Object -First 1
    try {
        if ($existing) {
            $body = @{ definition = $definition } | ConvertTo-Json -Depth 10
            Invoke-RestMethod -Uri "$FabricApi/workspaces/$($ws.id)/notebooks/$($existing.id)/updateDefinition" -Headers (Get-Headers) -Method Post -Body $body | Out-Null
            Write-Host "  [OK] zaktualizowano notebook $name" -ForegroundColor Green
        } else {
            $body = @{ displayName = $name; definition = $definition } | ConvertTo-Json -Depth 10
            $r = Invoke-WebRequest -Uri "$FabricApi/workspaces/$($ws.id)/notebooks" -Headers (Get-Headers) -Method Post -Body $body
            if ($r.StatusCode -eq 202) {
                $op = $r.Headers.Location | Select-Object -First 1
                do { Start-Sleep 5; $st = Invoke-RestMethod -Uri $op -Headers (Get-Headers) } while ($st.status -in 'Running', 'NotStarted')
            }
            Write-Host "  [OK] utworzono notebook $name" -ForegroundColor Green
        }
    } catch {
        Write-Host "  [BLAD] $name :: $($_.Exception.Message)" -ForegroundColor Yellow
        if ($_.ErrorDetails.Message) { Write-Host "         $($_.ErrorDetails.Message)" -ForegroundColor Yellow }
    }
}

Write-Host "`nGotowe: https://app.fabric.microsoft.com/groups/$($ws.id)" -ForegroundColor Cyan
