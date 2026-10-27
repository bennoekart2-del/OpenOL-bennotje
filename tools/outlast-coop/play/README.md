# Play kit: host and join helpers

Two small PowerShell scripts (Windows PowerShell 5.1 or newer) for the "How to play" steps in [../README.md](../README.md).
They download nothing, never change the firewall, the router or Steam files, and touch only what you point them at.

| Script | What it does |
|---|---|
| `install.ps1 [-SteamGame] [-Target] [-HostIp] [-Name]` (or double-click `INSTALL-OUTLAST-COOP.bat` in the repository root) | Does everything below in one go: a window asks where Outlast is installed (the Steam install is pre-selected) and a second one where the co-op copy goes (an `OutlastCoop` folder is made there), then two questions (are you hosting, your name). It checks the Whistleblower DLC, copies the game, downloads OpenOL 2.1.0 and refuses it unless its SHA-256 matches, applies the native patch (keeps `OLGame_original.exe`), writes the connection settings (room `DEFAULT`, the relay inside the game) into `DefaultMultiplayer.ini` and `OLMultiplayer.ini`, turns off pause-on-focus-loss, and puts an "Outlast Co-op" shortcut (`-nosteam`) on the desktop. Re-running skips finished steps. Never writes to the Steam folder. **Not run on a real PC yet.** |
| `host.ps1 -Relay <OpenOL_Relay.exe> [-Port 7777] [-TriggerRadius 3000]` | Prints this PC's IPv4 addresses and the manual steps (router port, firewall prompt), then runs the relay in the window. `-TriggerRadius` needs the patched relay (`../relay-patches`). |
| `join.ps1 -GameDir <game copy> -HostIp <address> [-Port] [-Name] [-Room] [-SyncEnemies False]` | Writes `OLGame\Config\OLMultiplayer.ini` of the copy you name (dated backup first, other keys kept). Warns if `OLGame.exe` is not the OpenOL 2.1.0 exe of Steam build 576074; refuses a folder inside `steamapps` unless `-Force`. |

Rooms: the standalone relay uses `PUBLIC` (the default of `join.ps1`); the relay inside the game uses `DEFAULT` (`-Room DEFAULT`).

Tested on one PC, with a throwaway folder: `join.ps1` on an existing ini (backup, keys replaced, other sections kept), on a missing ini, and the `steamapps` guard;
`host.ps1` with the patched relay (UDP bound, address list and notes printed). Not tested: two PCs.

## Native patch (no Python)
`apply-native-patch.ps1 -Exe <OLGame.exe> -Out <patched.exe>` applies the one-owner map-enemy fix to a copy of OpenOL 2.1.0's `OLGame.exe` using only PowerShell (a port of `../exe-patch/apply_patch.py`). It refuses any exe with the wrong SHA-256, never overwrites its input, and produces the same bytes as the Python tool. Put the patched exe in a game copy, keep the original, and patch every player's copy. See `../exe-patch/README.md`.
