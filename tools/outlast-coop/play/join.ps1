<#
.SYNOPSIS
  Point a COPY of Outlast (with OpenOL 2.1.0 installed) at a host: writes OLGame\Config\OLMultiplayer.ini.
.EXAMPLE
  .\join.ps1 -GameDir "D:\Games\Outlast-coop" -HostIp 192.168.1.20 -Name Alice
  .\join.ps1 -GameDir "D:\Games\Outlast-coop" -HostIp 127.0.0.1 -Room DEFAULT   # host using the relay inside the game
.NOTES
  Changes only the ini of the folder you name, after saving a dated backup next to it. Downloads nothing, touches no
  Steam files, firewall or network settings. Refuses a folder inside a Steam library unless you pass -Force: play on a copy.
#>
param(
    [Parameter(Mandatory)][string]$GameDir,
    [Parameter(Mandatory)][string]$HostIp,
    [int]$Port = 7777,
    [string]$Name = "Player",
    [string]$Room = "PUBLIC",          # standalone relay: PUBLIC; relay inside the game (F6 > Relay): DEFAULT
    [string]$Password = "",
    [ValidateSet("True", "False")][string]$SyncEnemies = "True",   # False = each player keeps own, unshared map enemies (no double enemies)
    [switch]$Force
)
$ErrorActionPreference = "Stop"
$known = "2e58afbb1203d04476581f34216428d1dfc96228e5f3df8c6881323c56c93346"   # OLGame.exe of OpenOL 2.1.0 on Steam build 576074

$exe = Join-Path $GameDir "Binaries\Win64\OLGame.exe"
if (-not (Test-Path $exe)) { throw "No Binaries\Win64\OLGame.exe in '$GameDir'. Pass the root of the game copy." }
if (($GameDir -match "steamapps") -and -not $Force) {
    throw "'$GameDir' looks like a Steam library folder. Copy the game to another folder and use that copy (or pass -Force)."
}
$patched = ""                                                     # the same exe with ..\exe-patch applied
$blob = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\exe-patch\olfix.json"
if (Test-Path $blob) { $patched = (Get-Content -Raw $blob | ConvertFrom-Json).output_sha256 }
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
if ($hash -ne $known -and $hash -ne $patched) {
    Write-Warning "OLGame.exe does not match OpenOL 2.1.0 on Steam build 576074 (SHA-256 $hash). Is OpenOL installed over this copy, and is it the same game build?"
}
if ($Name -match "[=\r\n]" -or $Password -match "[\r\n]") { throw "Name/Password must not contain '=' or line breaks." }

$ini = Join-Path $GameDir "OLGame\Config\OLMultiplayer.ini"
$want = [ordered]@{
    IP = $HostIp; UdpPort = "$Port"; UserName = $Name; RoomCode = $Room; Password = $Password
    SyncInteractable = "True"; SyncEnemies = $SyncEnemies; SyncMatinees = "True"; SyncPickups = "True"
}
$lines = @()
if (Test-Path $ini) {
    $bak = "$ini.bak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    Copy-Item $ini $bak
    Write-Host "Backup: $bak"
    $lines = Get-Content $ini
}
$out = New-Object System.Collections.Generic.List[string]
$inSection = $false; $seen = @{}
foreach ($l in $lines) {
    if ($l -match "^\[(.+)\]\s*$") {
        if ($inSection) { foreach ($k in $want.Keys) { if (-not $seen[$k]) { $out.Add("$k=$($want[$k])") } } }
        $inSection = ($Matches[1] -eq "OLGame.OLNetworkConfig")
        $out.Add($l); continue
    }
    if ($inSection -and $l -match "^([^=;]+)=") {
        $k = $Matches[1].Trim()
        if ($want.Contains($k)) { $out.Add("$k=$($want[$k])"); $seen[$k] = $true; continue }
    }
    $out.Add($l)
}
if (-not $lines) {
    $out.Add("[OLGame.OLNetworkConfig]")
    foreach ($k in $want.Keys) { $out.Add("$k=$($want[$k])") }
} elseif ($inSection) {
    foreach ($k in $want.Keys) { if (-not $seen[$k]) { $out.Add("$k=$($want[$k])") } }
}
[System.IO.File]::WriteAllLines($ini, $out, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Wrote $ini"
Write-Host "  host ${HostIp}:$Port, room $Room, name $Name, SyncEnemies=$SyncEnemies"
Write-Host "Start the game from this copy (Binaries\Win64\OLGame.exe), the host's relay must already be running."
