param(
    [string]$DemoDateKey = "2026-05-20",
    [string]$RestoreLatestDateKey = "2026-05-19",
    [int]$TemplateId = 2,
    [int]$PacketGapMinutes = 64,
    [switch]$PauseBetweenPhases,
    [switch]$CleanupAfterDemo,
    [switch]$CleanupOnly,
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

function Wait-ForUser {
    param(
        [string]$Message
    )

    if (-not $PauseBetweenPhases) {
        return
    }

    Write-Host ""
    Read-Host $Message | Out-Null
}

function Invoke-Cleanup {
    Write-Phase "CLEANUP - Xoa result va du lieu demo ngay 2026-05-20"

    Invoke-Step -Label "Demo cleanup utility (Firebase + local folder cleanup)" -Arguments @(
        "cleanup_demo_state.py",
        "--demo-date-key", $DemoDateKey,
        "--restore-latest-date-key", $RestoreLatestDateKey
    ) + $(if ($DryRun) { @("--dry-run") } else { @() })

    Invoke-Step -Label "Prune local Layer1 / benchmark outputs ve moc 2026-05-19" -Arguments @(
        "main.py",
        "--prune-output-after-local-date", $RestoreLatestDateKey
    )

    if (-not $DryRun) {
        Invoke-Step -Label "Refresh local latest-only Layer0 tu moc da restore" -Arguments @(
            "main.py",
            "--only-layer0",
            "--latest-only"
        )
    }
}

Write-Host "Backend demo web flow" -ForegroundColor Green
Write-Host "Script path: $PSCommandPath"
Write-Host "Working dir: $scriptDir"
Write-Host "Dry run: $($DryRun.IsPresent)"
Write-Host "Note: script nay bo qua pha full-history cham. Neu can, chay prepare_historical_result_snapshot.ps1 truoc." -ForegroundColor DarkYellow

if ($CleanupOnly) {
    Invoke-Cleanup
    Write-Host ""
    Write-Host "Cleanup-only flow complete." -ForegroundColor Green
    return
}

Write-Phase "PHASE 2 - Bootstrap baseline demo ngay 2026-05-20"
Invoke-Step -Label "Inject baseline 00:00 -> 12:00 vao Firebase, sync ve Layer0 local, roi build Layer1" -Arguments @(
    "main.py",
    "--demo-bootstrap-day",
    "--inject-date-key", $DemoDateKey,
    "--server-cycle-skip-super-table"
)
Invoke-Step -Label "Snapshot lai result de web co them baseline 2026-05-20" -Arguments @(
    "main.py",
    "--only-result",
    "--publish-result",
    "--result-mode", "snapshot",
    "--result-payload-scope", "full",
    "--result-runtime-experiment", "auto"
)

Wait-ForUser -Message "Pha 2 xong. Mo web neu muon chot baseline 20/5, roi nhan Enter de bat dau pha dong"

Write-Phase "PHASE 3 - Append dong ban ghi demo len result"
Invoke-Step -Label "Inject scenario demo vao Firebase, sync local, build Layer1, roi append len result" -Arguments @(
    "main.py",
    "--server-cycle-demo",
    "--inject-telemetry-template", "$TemplateId",
    "--inject-date-key", $DemoDateKey,
    "--inject-packet-gap-minutes", "$PacketGapMinutes",
    "--server-cycle-skip-super-table"
)

if ($CleanupAfterDemo) {
    Wait-ForUser -Message "Demo dong da xong. Nhan Enter de xoa result va du lieu demo 20/5"
    Invoke-Cleanup
}

Write-Host ""
Write-Host "Hoan tat flow demo web." -ForegroundColor Green
Write-Host "Goi y:" -ForegroundColor DarkGreen
Write-Host "  - Lich su that: chuan bi rieng bang prepare_historical_result_snapshot.ps1."
Write-Host "  - Pha 2: chart co them baseline 20/5 sau khi du lieu duoc ghi vao Firebase va sync ve local."
Write-Host "  - Pha 3: chart tiep tuc di dong khi record moi duoc inject, sync local va append len result."
if ($CleanupAfterDemo) {
    Write-Host "  - Cleanup: xoa result va xoa du lieu demo 20/5 tren Firebase/local."
}
