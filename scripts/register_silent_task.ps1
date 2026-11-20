#Requires -Version 5.1
<#
    Csendes, napi helyi futtatás Windows Feladatütemezővel.

    A feladat pythonw.exe-vel fut, ezért nincs konzolablak, és nem nyit
    böngészőt. A check parancs csak esemény esetén küld értesítést a
    bekapcsolt Discord/Telegram csatornákra (új sorozat, indulás,
    lejárat előtti figyelmeztetés), és csendben frissíti a helyi
    dashboardot a site/index.html fájlban.

    Példa:
        powershell -ExecutionPolicy Bypass -File scripts\register_silent_task.ps1
        powershell -ExecutionPolicy Bypass -File scripts\register_silent_task.ps1 -Time "08:30"
        powershell -ExecutionPolicy Bypass -File scripts\register_silent_task.ps1 -Python "C:\Python312\pythonw.exe"

    Törlés:
        Unregister-ScheduledTask -TaskName "MapPluszNapi" -Confirm:$false
#>
[CmdletBinding()]
param(
    [string]$TaskName = "MapPluszNapi",
    [string]$Time = "09:00",
    [string]$Python = "",
    [string]$Config = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $Config) {
    $Config = Join-Path $ProjectRoot "config.toml"
}
if (-not (Test-Path -LiteralPath $Config)) {
    throw "Nem találom a konfigurációt: $Config. Először futtasd: python -m allampapir_ertesito setup"
}

if (-not $Python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Nem találom a Pythont. Add meg a -Python paraméterrel a pythonw.exe útvonalát."
    }
    $Python = $pythonCommand.Source
}
$pythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $Python = $pythonCommand.Source
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Nem találom a Python futtatható programot: $Python"
}

if ([System.IO.Path]::GetFileName($Python) -ne "pythonw.exe") {
    $candidate = Join-Path (Split-Path $Python) "pythonw.exe"
    if (Test-Path -LiteralPath $candidate) {
        $Python = $candidate
    } else {
        Write-Warning "Nem található pythonw.exe; a python.exe rövid konzolablakot nyithat."
    }
}

$argument = "-m allampapir_ertesito check --config `"$Config`" --dashboard --no-calculator"
$action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument $argument `
    -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "MÁP+ eseményértesítés csendben, helyi dashboard frissítéssel" `
    -Force | Out-Null

Write-Host "A csendes feladat létrejött: $TaskName"
Write-Host "  Python: $Python"
Write-Host "  Projekt: $ProjectRoot"
Write-Host "  Config: $Config"
Write-Host "  Időpont: $Time"
Write-Host ""
Write-Host "A feladat az aktuális felhasználóhoz jött létre, és jellemzően"
Write-Host "bejelentkezve fut. Ha a laptop alszik, a StartWhenAvailable"
Write-Host "a következő ébredéskor pótolja."
Write-Host ""
Write-Host "Azonnali teszt: Start-ScheduledTask -TaskName `"$TaskName`""
Write-Host "Törlés: Unregister-ScheduledTask -TaskName `"$TaskName`" -Confirm:`$false"
