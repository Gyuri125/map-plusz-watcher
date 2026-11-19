#Requires -Version 5.1
<#
    Napi (vagy naponta többszöri) ellenőrzés beállítása a Windows Feladatütemezőben.

    Példák:
        powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
        powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Time "09:00","15:00"
        powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Python "C:\venv\Scripts\python.exe"

    A feladat az aktuális felhasználó nevében fut, és a projekt gyökeréből
    indítja a `python -m allampapir_ertesito check` parancsot.
#>
[CmdletBinding()]
param(
    [string]$TaskName = "MapPluszErtesito",
    [string[]]$Time = @("09:00"),
    [string]$Python = "python",
    [string]$Config = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $Config) {
    $Config = Join-Path $ProjectRoot "config.toml"
}
if (-not (Test-Path -LiteralPath $Config)) {
    throw "Nem találom a konfigurációt: $Config. Először futtasd: python -m allampapir_ertesito init"
}

$pythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw "Nem találom a Python futtatható programot: $Python. Add meg a -Python paraméterrel."
}
$pythonPath = $pythonCommand.Source
if (-not $pythonPath) {
    $pythonPath = $pythonCommand.Path
}

$argument = "-m allampapir_ertesito check --config `"$Config`""
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $argument -WorkingDirectory $ProjectRoot
$triggers = @()
foreach ($item in $Time) {
    $triggers += New-ScheduledTaskTrigger -Daily -At $item
}
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Description "MÁP+ állampapír sorozatok figyelése és értesítése" `
    -Force | Out-Null

Write-Host "A feladat létrejött: $TaskName"
Write-Host "  Python: $pythonPath"
Write-Host "  Projekt: $ProjectRoot"
Write-Host "  Konfiguráció: $Config"
Write-Host "  Időpontok: $($Time -join ', ')"
Write-Host ""
Write-Host "Ellenőrzés: Get-ScheduledTask -TaskName `"$TaskName`""
Write-Host "Azonnali futtatás: Start-ScheduledTask -TaskName `"$TaskName`""
