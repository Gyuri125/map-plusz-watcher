#Requires -Version 5.1
<#
    A korábban létrehozott ütemezett feladat törlése.
#>
[CmdletBinding()]
param(
    [string]$TaskName = "MapPluszErtesito"
)

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "Nincs ilyen feladat: $TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "A feladat törölve: $TaskName"
