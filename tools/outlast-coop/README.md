# Outlast co-op on OpenOL 2.1.0: patches, play kit and tests

Own development on top of [OpenOL](https://github.com/ShyKiss/OpenOL) (a modified Outlast client with a multiplayer beta). Nothing here is
offered to or maintained with the OpenOL authors. Everything in `tools/outlast-coop/` is MIT licensed (see `LICENSE`); the rest of this repository
is the upstream code under its own terms (the upstream repository has no license file). This folder contains no Outlast or OpenOL files, only
patches, scripts and tests.

[README_RU.md](README_RU.md): the same guide in Russian.

Tested on: Outlast (Steam build 576074, Whistleblower DLC installed), OpenOL 2.1.0 release, Windows 11, two game copies on one PC.
**Not tested: two PCs, the internet, three or more players.**

## What is here

| Folder | What |
|---|---|
| `exe-patch/` | A native patch for `OLGame.exe` of OpenOL 2.1.0: one real copy of every map enemy instead of two (see below). `apply_patch.py` (Python) and `play/apply-native-patch.ps1` (PowerShell) apply it; both refuse any exe with another SHA-256 and never overwrite their input. |
| `relay-patches/` | Three patches for `OpenOL-Relay` (commit `b9def512`): trigger radius filter, the enemy packet ids the 2.1.0 client really sends, and the late-join snapshot the console relay never sent. Files only; apply them to your own copy of the relay source. |
| `play/` | `host.ps1` (run the relay, show this PC's addresses), `join.ps1` (write `OLMultiplayer.ini` of a game copy, with a backup), `apply-native-patch.ps1`. |
| `harness/` | The automated tests: a suite that starts real game clients, a logging proxy, scripted peers, a game-free relay protocol test, a memory census of enemies. Windows only. |
| `../../Development/Src/Multiplayer/Src/EnemyChannel.cpp` | The same one-owner rule written in the OpenOL source (not compiled by us: building needs the non-public Outlast source). |

## The enemy fix

Every client runs the AI of each map-placed enemy and announces it; every client turns what it receives into a puppet, so two copies of one
enemy stood in one place and both attacked. With the patch, when two copies of one enemy meet (same class, within 150 units) the copy of the
client with the **lower player id** stays real; the other client destroys its own copy and keeps the puppet. Since v7 the same goes for story enemies
that the two clients spawn at different times (each client's Kismet spawns them when its own player gets there, so the first copy has often run off before the
second is born): a new enemy of ours born where a partner's enemy of that class was born is dropped before it is announced. Limits: two different enemies of
the same class closer than 150 units (or born at the same spot) can be merged by mistake; both players should use the patched exe.

## Use (short)

Easiest: download this repository (Code > Download ZIP), unzip it, double-click `INSTALL-OUTLAST-COOP.bat` and answer two questions. It does steps 1 to 4
below for you (see `play/README.md`). By hand:

1. Copy your Outlast install (needs the Whistleblower DLC), install the OpenOL 2.1.0 release over the copy. Never touch the Steam folder itself.
2. Everyone: `play\apply-native-patch.ps1 -Exe <copy>\Binaries\Win64\OLGame.exe -Out OLGame_patched.exe`, keep the original, put the patched exe in the copy.
3. Host: build the relay (see `relay-patches/README.md`) or use the release `OpenOL_Relay`, then `play\host.ps1 -Relay <OpenOL_Relay.exe>`; forward UDP 7777 or use a VPN network. Room `PUBLIC`.
4. Everyone: `play\join.ps1 -GameDir <copy> -HostIp <host address> -Name <name>`, start the game from the copy, Multiplayer > Connect, then New Game.

Details, firewall notes and the known issues are in [README_RU.md](README_RU.md) and [play/README.md](play/README.md).

## Test results (2026-10-22)

`harness/suite.py` on the patched exe, groups P, A, B, C, D, E, F, N, H: **67 PASS, 4 XFAIL, 0 FAIL**. The four XFAIL are known bugs of the relays
(S9 to S11: the console relay never sends the late-join snapshot, fixed by `relay-patches/0003`; E5: the relay inside the exe stores enemy
positions under another packet type). Group G (menu path, New Game, rejoin through the menu) 6 of 6, run on its own because it needs real mouse
and keyboard. The same suite on the original exe shows the enemy duplication (checks A4 and A4b are XFAIL there): the proof that the tests can fail.
Read the unverified list in [harness/README.md](harness/README.md) before trusting this for a long session.

## Not done

Pickups and pushable objects in a real game (protocol-tested only), a play session over the internet. Shared checkpoint loads are in the exe patch since v5
(`harness/shared_cp_live.py` SC1 to SC5 PASS). Story triggers that wait until your hero is near them are in v6 (game-free `exe-patch/emutest.py` 18/18 PASS;
`harness/trigger_near_live.py` with real clients **not run yet**). Late copies of story enemies are merged since v7 (`exe-patch/emutest.py` L0 to L10 PASS,
**not tested in-game yet**).
