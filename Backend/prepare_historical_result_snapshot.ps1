param(
    [string]$HistoricalStartDate = "2026-04-01",
    [string]$HistoricalEndDate = "2026-05-19",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

function Write-Phase {
    param(
        [string]$Title
    )

    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkGreen
    Write-Host $Title -ForegroundColor Green
    Write-Host ("=" * 78) -ForegroundColor DarkGreen
}

function Invoke-Step {
    param(
        [string]$Label,
        [string[]]$Arguments
    )

    $commandText = "python " + ($Arguments -join " ")
    Write-Host ""
    Write-Host "[STEP] $Label" -ForegroundColor Cyan
    Write-Host "       $commandText" -ForegroundColor DarkCyan

    if ($DryRun) {
        return
    }

    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Label (exit code $LASTEXITCODE)"
    }
}

Write-Host "Historical result snapshot prep" -ForegroundColor Green
Write-Host "Script path: $PSCommandPath"
Write-Host "Working dir: $scriptDir"
Write-Host "Dry run: $($DryRun.IsPresent)"

Write-Phase "PHASE 1 - Snapshot lich su that len result"
Invoke-Step -Label "Layer0 full-history $HistoricalStartDate -> $HistoricalEndDate" -Arguments @(
    "main.py",
    "--only-layer0",
    "--full-history",
    "--start-date", $HistoricalStartDate,
    "--end-date", $HistoricalEndDate
)
Invoke-Step -Label "Build Layer1 tu local Layer0" -Arguments @(
    "main.py",
    "--only-layer1"
)
Invoke-Step -Label "Snapshot full result tu local Layer1" -Arguments @(
    "main.py",
    "--only-result",
    "--publish-result",
    "--result-mode", "snapshot",
    "--result-payload-scope", "full",
    "--result-runtime-experiment", "auto"
)

Write-Host ""
Write-Host "Hoan tat pha chuan bi lich su that." -ForegroundColor Green
Write-Host "Goi y:" -ForegroundColor DarkGreen
Write-Host "  - Script nay nen chay truoc va chi can chay 1 lan khi chuan bi demo."
Write-Host "  - Sau do dung run_demo_web_flow.ps1 de chay baseline 20/5 va pha dong."
