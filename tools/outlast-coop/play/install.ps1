<#
.SYNOPSIS
  One-step setup of Outlast co-op: copies your Steam Outlast to a new folder, installs OpenOL 2.1.0 into the copy,
  applies the native patch (one owner per map enemy, shared checkpoint loads, story triggers by distance) and writes
  the connection settings. Run it again any time: finished steps are skipped.
.EXAMPLE
  Double-click INSTALL-OUTLAST-COOP.bat in the repository root, or:
  powershell -ExecutionPolicy Bypass -File install.ps1
  powershell -ExecutionPolicy Bypass -File install.ps1 -Target D:\OutlastCoop -HostIp 26.10.20.30 -Name Alice
.NOTES
  Never changes the Steam folder itself (it is only read). Downloads one file, the OpenOL 2.1.0 release from
  github.com/ShyKiss/OpenOL, and refuses it unless its SHA-256 matches. The original OLGame.exe of the copy is kept
  as OLGame_original.exe. No firewall, router or Steam settings are touched.
#>
param(
    [string]$SteamGame = "",      # your Outlast install; empty: a window asks (the Steam install is pre-selected)
    [string]$Target = "",         # the co-op copy; empty: a window asks for the folder to put OutlastCoop in
    [string]$HostIp = "",         # empty: ask. 127.0.0.1 = you host
    [string]$Name = "",
    [int]$Port = 7777,
    [string]$Room = "DEFAULT",    # the relay inside the game (F6 > Relay) only knows DEFAULT
    [switch]$NoShortcut
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"                       # Invoke-WebRequest is many times slower with the progress bar on
$here = Split-Path -Parent $MyInvocation.MyCommand.Path        # not $PSScriptRoot: Windows PowerShell 5.1 can leave it empty

$OPENOL_URL = "https://github.com/ShyKiss/OpenOL/releases/download/2.1.0/OpenOL.zip"
$OPENOL_SHA = "b301b267d4c2e26815b6b7f11267ecae493c65db2ad523ab2d23512d9db2d67d"
$blob = Get-Content -Raw (Join-Path $here "..\exe-patch\olfix.json") | ConvertFrom-Json
$EXE_OPENOL = $blob.input_sha256                                # OLGame.exe of OpenOL 2.1.0 (Steam build 576074)
$EXE_PATCHED = $blob.output_sha256                              # the same exe with this repository's patch

function Step($n, $text) { Write-Host ""; Write-Host "[$n/6] $text" -ForegroundColor Cyan }
function Sha($path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }
function Set-IniKeys($path, $section, $values) {
    # Sets keys in the first [section] of an ini (adds missing ones at its end, adds the section if absent); everything else is kept.
    $lines = if (Test-Path $path) { @(Get-Content -LiteralPath $path) } else { @() }
    $out = New-Object System.Collections.Generic.List[string]
    $state = 0; $seen = @{}                                   # 0 before the section, 1 inside it, 2 after it
    foreach ($l in $lines) {
        if ($l -match "^\[(.+)\]\s*$") {
            if ($state -eq 1) { foreach ($k in $values.Keys) { if (-not $seen[$k]) { $out.Add("$k=$($values[$k])") } }; $state = 2 }
            elseif ($state -eq 0 -and $Matches[1] -eq $section) { $state = 1 }
            $out.Add($l); continue
        }
        if ($state -eq 1 -and $l -match "^([^=;]+)=" -and $values.Contains($Matches[1].Trim())) {
            $k = $Matches[1].Trim(); $out.Add("$k=$($values[$k])"); $seen[$k] = $true; continue
        }
        $out.Add($l)
    }
    if ($state -eq 1) { foreach ($k in $values.Keys) { if (-not $seen[$k]) { $out.Add("$k=$($values[$k])") } } }
    if ($state -eq 0) { $out.Add("[$section]"); foreach ($k in $values.Keys) { $out.Add("$k=$($values[$k])") } }
    [System.IO.File]::WriteAllLines($path, $out, (New-Object System.Text.UTF8Encoding($false)))
}

# ---- 1. where is the game --------------------------------------------------------------------------------
function Pick-Folder($description, $start) {
    # A "choose folder" window; returns "" when cancelled.
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = $description
    $dlg.ShowNewFolderButton = $true
    if ($start -and (Test-Path $start)) { $dlg.SelectedPath = $start }
    $owner = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true }   # keeps the window in front of the console
    $res = $dlg.ShowDialog($owner)
    $owner.Dispose()
    if ($res -eq [System.Windows.Forms.DialogResult]::OK) { return $dlg.SelectedPath }
    return ""
}

Step 1 "Where is Outlast installed?"
$guess = ""
$steam = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -Name SteamPath -ErrorAction SilentlyContinue).SteamPath
if ($steam) {                                                   # pre-select the Steam install if there is one
    $libs = New-Object System.Collections.Generic.List[string]
    $libs.Add($steam)
    $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
    if (Test-Path $vdf) {
        foreach ($m in [regex]::Matches((Get-Content -Raw $vdf), '"path"\s+"([^"]+)"')) { $libs.Add(($m.Groups[1].Value -replace '\\\\', '\')) }
    }
    foreach ($lib in $libs) {
        $cand = Join-Path $lib "steamapps\common\Outlast"
        if (Test-Path (Join-Path $cand "Binaries\Win64\OLGame.exe")) { $guess = $cand; break }
    }
}
while (-not $SteamGame) {
    Write-Host "  A window opens: select your Outlast folder (the one with the Binaries and OLGame folders in it)."
    $pick = Pick-Folder "Select your Outlast folder (it contains the Binaries and OLGame folders)." $guess
    if (-not $pick) { Fail "no folder selected." }
    $up = $pick
    for ($n = 0; $n -lt 3 -and $up; $n++) {                      # also accept Binaries or Binaries\Win64 picked by mistake
        if (Test-Path (Join-Path $up "Binaries\Win64\OLGame.exe")) { $SteamGame = $up; break }
        $up = [System.IO.Path]::GetDirectoryName($up)            # "" or $null at a drive root, which ends the loop
    }
    if (-not $SteamGame) { Write-Host "  '$pick' is not an Outlast folder (no Binaries\Win64\OLGame.exe). Try again." -ForegroundColor Yellow; $guess = $pick }
}
if (-not (Test-Path (Join-Path $SteamGame "Binaries\Win64\OLGame.exe"))) { Fail "'$SteamGame' is not an Outlast folder (no Binaries\Win64\OLGame.exe)." }
$SteamGame = (Resolve-Path -LiteralPath $SteamGame).Path
Write-Host "  Game: $SteamGame"
if (-not (Test-Path (Join-Path $SteamGame "OLGame\CookedPCConsoleDLC\DLC_Intro_Persistent.upk"))) {
    Fail "the Whistleblower DLC is not in that folder. OpenOL's multiplayer needs it: install it in Steam, then run this again."
}

# ---- 2. copy the game ---------------------------------------------------------------------------------------
if (-not $Target) {
    $default = [System.IO.Path]::GetPathRoot($SteamGame)
    Write-Host "  A second window opens: select where the co-op copy should go (a folder 'OutlastCoop' is made inside it, about 6.5 GB)."
    $parent = Pick-Folder "Where should the co-op copy go? A folder 'OutlastCoop' is made inside the folder you select (about 6.5 GB)." $default
    if (-not $parent) { Fail "no folder selected." }
    $Target = if ((Split-Path -Leaf $parent) -ieq "OutlastCoop") { $parent } else { Join-Path $parent "OutlastCoop" }
}
$Target = [System.IO.Path]::GetFullPath($Target)
if ($Target.TrimEnd('\') -ieq $SteamGame.TrimEnd('\')) { Fail "the co-op copy cannot be the game folder itself. Choose another folder." }
if ($Target.StartsWith($SteamGame.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) { Fail "the co-op copy cannot be inside the game folder. Choose another folder." }
if ($Target -match "\\steamapps\\") { Fail "'$Target' is inside a Steam library. Choose a folder outside steamapps." }
$exe = Join-Path $Target "Binaries\Win64\OLGame.exe"
Step 2 "Copying the game to $Target"
if (Test-Path $exe) {
    Write-Host "  Already there, not copied again."
} else {
    $drive = Get-PSDrive -Name $Target.Substring(0, 1) -ErrorAction SilentlyContinue
    if ($drive -and $drive.Free -lt 7GB) { Fail "less than 7 GB free on $($Target.Substring(0, 2)). The copy needs about 6.5 GB." }
    Write-Host "  About 6 GB, this takes a few minutes..."
    robocopy $SteamGame $Target /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "copying failed (robocopy exit code $LASTEXITCODE)." }
    if (-not (Test-Path $exe)) { Fail "the copy has no Binaries\Win64\OLGame.exe." }
    Write-Host "  Done."
}

# ---- 3. install OpenOL 2.1.0 --------------------------------------------------------------------------------
Step 3 "Installing OpenOL 2.1.0 into the copy"
$h = Sha $exe
$keep = Join-Path $Target "Binaries\Win64\OLGame_original.exe"
if ($h -ne $EXE_OPENOL -and $h -ne $EXE_PATCHED -and (Test-Path $keep) -and ((Sha $keep) -eq $EXE_OPENOL)) {
    Write-Host "  An older co-op patch is installed: starting again from the kept OLGame_original.exe."
    Copy-Item $keep $exe -Force
    $h = $EXE_OPENOL
}
if ($h -eq $EXE_OPENOL -or $h -eq $EXE_PATCHED) {
    Write-Host "  Already installed."
} else {
    $zip = Join-Path $env:TEMP "OpenOL-2.1.0.zip"
    if (-not ((Test-Path $zip) -and ((Sha $zip) -eq $OPENOL_SHA))) {
        Write-Host "  Downloading $OPENOL_URL"
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $OPENOL_URL -OutFile $zip -UseBasicParsing
    }
    $zh = Sha $zip
    if ($zh -ne $OPENOL_SHA) { Remove-Item $zip -Force; Fail "the downloaded OpenOL.zip has the wrong SHA-256 ($zh). Nothing was installed." }
    Write-Host "  Download verified, unpacking..."
    Expand-Archive -LiteralPath $zip -DestinationPath $Target -Force
    $h = Sha $exe
    if ($h -ne $EXE_OPENOL) {
        Fail "after installing OpenOL the exe is not the expected one ($h). Your Outlast may be a different version than Steam build 576074."
    }
    Write-Host "  Done."
}

# ---- 4. apply the patch -------------------------------------------------------------------------------------
Step 4 "Applying the co-op patch to OLGame.exe"
if ($h -eq $EXE_PATCHED) {
    Write-Host "  Already patched."
} else {
    $tmp = "$exe.patched"
    if (Test-Path $tmp) { Remove-Item $tmp -Force }
    & (Join-Path $here "apply-native-patch.ps1") -Exe $exe -Out $tmp -Blob (Join-Path $here "..\exe-patch\olfix.json") | Out-Host
    if ((Sha $tmp) -ne $EXE_PATCHED) { Remove-Item $tmp -Force; Fail "the patched exe is not the expected build. OLGame.exe was not changed." }
    $orig = Join-Path $Target "Binaries\Win64\OLGame_original.exe"
    if (Test-Path $orig) { Remove-Item $exe -Force } else { Move-Item $exe $orig }
    Move-Item $tmp $exe
    Write-Host "  Done. The unpatched exe is kept as OLGame_original.exe."
}

# ---- 5. connection settings ---------------------------------------------------------------------------------
Step 5 "Connection settings"
if (-not $HostIp) {
    $ans = Read-Host "  Will YOU host the game? (y/n)"
    if ($ans -match "^[yY]") {
        $HostIp = "127.0.0.1"
    } else {
        $HostIp = (Read-Host "  The host's IP address (their Radmin VPN / ZeroTier / Tailscale address, or public IP)").Trim()
        if (-not $HostIp) { Fail "no host address given. Run again and enter it, or pass -HostIp." }
    }
}
if (-not $Name) {
    $Name = (Read-Host "  Your player name (Enter = $env:USERNAME)").Trim()
    if (-not $Name) { $Name = $env:USERNAME }
}
$Name = $Name -replace "[=\r\n]", ""
# The game builds OLGame\Config\OLMultiplayer.ini and OLEngine.ini from the Default*.ini files (and rebuilds them when those change),
# so the values go into the Default files; the built files, when they already exist, get the same values right away.
$cfg = Join-Path $Target "OLGame\Config"
$net = [ordered]@{ IP = $HostIp; UdpPort = "$Port"; UserName = $Name; RoomCode = $Room; Password = "" }
foreach ($f in @("DefaultMultiplayer.ini", "OLMultiplayer.ini")) {
    $p = Join-Path $cfg $f
    if ((Test-Path $p) -or $f -like "Default*") { Set-IniKeys $p "OLGame.OLNetworkConfig" $net }
}
Write-Host "  Host $HostIp, port $Port, room $Room, name $Name"
foreach ($f in @("DefaultEngine.ini", "OLEngine.ini")) {   # a paused game stops its network tick: keep running when alt-tabbed
    $p = Join-Path $cfg $f
    if (Test-Path $p) { Set-IniKeys $p "Engine.Engine" ([ordered]@{ bPauseOnLossOfFocus = "FALSE" }) }
}
Write-Host "  The game keeps running when its window loses focus (needed for alt-tab and for two windows on one PC)."

# ---- 6. shortcut --------------------------------------------------------------------------------------------
Step 6 "Desktop shortcut"
if ($NoShortcut) {
    Write-Host "  Skipped."
} else {
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Outlast Co-op.lnk"
    $sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $sc.TargetPath = $exe
    $sc.Arguments = "-nosteam"                                 # keeps your Steam Cloud saves and profile out of the modded game
    $sc.WorkingDirectory = Split-Path $exe
    $sc.Save()
    Write-Host "  Created 'Outlast Co-op' on your desktop."
}

Write-Host ""
Write-Host "All set." -ForegroundColor Green
if ($HostIp -eq "127.0.0.1") {
    Write-Host "  You host: start 'Outlast Co-op', press F6, Relay tab, Start Relay, close F6, then Multiplayer > Connect."
    Write-Host "  Give your friend your VPN address (Radmin VPN / ZeroTier / Tailscale), or forward UDP port $Port on your router."
} else {
    Write-Host "  Start 'Outlast Co-op' after the host has started the relay, then Multiplayer > Connect."
}
Write-Host "  When the corner shows '2 players', both choose New Game."
