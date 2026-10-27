# Outlast Co-op: play Outlast with a friend

**[⬇ Download the installer (OutlastCoop-Installer.zip)](https://github.com/bennoekart2-del/OpenOL-bennotje/releases/latest/download/OutlastCoop-Installer.zip)**

**You need:** Windows and Outlast on Steam **with the Whistleblower DLC**. Every player needs their own copy of the game.

1. Download the zip above and unzip it, for example to your Desktop.
2. Double-click **`INSTALL-OUTLAST-COOP.bat`**. If Windows asks whether to run it, click *More info* and then *Run anyway*.
3. In the first window, select your Outlast folder. The Steam folder is usually already selected, so just click OK.
4. In the second window, choose where the co-op copy should go (it needs about 6.5 GB). Your Steam game is never changed.
5. Answer two questions: are you hosting, and what is your name. A friend who joins types the host's IP address.
6. Start **Outlast Co-op** from your desktop.

**To play together:**
- Both of you join the same free virtual LAN, such as [Radmin VPN](https://www.radmin-vpn.com/), ZeroTier or Tailscale. The joining player uses the host's address from that app.
- **The host:** press **F6**, open the **Relay** tab, click **Start Relay**, close the overlay with F6, then go to **Multiplayer > Connect**.
- **The friend:** go to **Multiplayer > Connect**.
- When the corner of the screen says **"2 players"**, both of you choose **New Game**.

What works: both players see each other, doors, enemies (one copy each), damage, death and respawn, shared checkpoint loads, and story events that wait until you are near them. More details are in [tools/outlast-coop](tools/outlast-coop/README.md). This is a fan project built on [OpenOL](https://github.com/ShyKiss/OpenOL) and the [G3RKA fork](https://github.com/G3RKA/OpenOL).

---

# OpenOL — Modified client of Outlast Game

<p align="center">
  <a href="./README.md">🇺🇸 English</a> /
  <a href="./README_RU.md">🇷🇺 Русский</a>
</p>

<img src="./docs/assets/OpenOL_1.webp" width="100%">

***NOTE (mainly for Red Barrels):** **In addition** to the files from this repository, you should still have the **original source files and a licensed copy of the game** (for content files, etc.). The files from this repository are provided only for **modding convenience***<p>
If you happen to have the original Outlast source files, you can add/replace them with these

The resulting `OLGame.exe`, along with `Core.upk`, `Engine.upk`, `OLGame.upk`, or any other (post-cook) `.upk` files to which you add UnrealScript, can be used to replace the original files in **your licensed Steam version of the game**.

## Currently, the modified source code allows you to:

### Content/Maps/Shaders

- Load original content/maps/shaders (including DLC)
- Load custom maps via a separate tab in the main menu (maps displayed in this tab must be placed in the `CookedPCConsole/Mods/Persistent` folder)
- Cook `.upk` files, saving textures and lighting in separate `.tfc` files (which are read from any subfolder of `CookedPCConsole`)
- Cook `.upk` files, saving `Textures`, `CharTextures `and `Lighting` within each .upk (without `.tfc` files). This is useful when you don't want to drag three separate `.tfc` files just for one `.upk`
- Adding a custom suffix to `RefShaderCache` when cooking `.upk` files
- Asset redirection for only-script packages (`.u`). For example, updated scripts from `OLGame.u` now take priority over original `OLGame.upk`, and loading order is: `.u` script -> group-referenced `.upk` (e.g. `menuassets.upk`) -> original `OLGame.upk`

### Multiplayer (beta)

- Connect to [OpenOL relays](https://github.com/ShyKiss/OpenOL-Relay) and play in multiplayer mode
- Influence other clients worlds (Doors/Triggers/Enemies/Cutscenes)
- Host a server directly from within the game (embedded relay)

### New Console Commands

- `Reload` reload current checkpoint
- `SpawnEnemy <Enemy> <Weapon> <ShouldAttack>` spawns enemy with specified weapon and attack control
- `ToggleSmoothCamera` toggles smooth camera setting
- `ToggleUnlockDoors` toggles whether player ignores locked/blocked doors
- `ToggleAllowGhostDoors` toggles ability to do "ghost door" glitch (e.g. for speedruns)
- `MaxFPS <Number>` alias for `Set Engine MaxSmoothedFramerate <Number>` command
- `Unlit` / `Lit` / `ToggleUnlit` sets/toggles viewmode to Unlit or Lit
- `SetGameSpeed <Number>` sets game speed

### Debug/Developer Menu

- Press **F6** in-game to open the ImGui overlay menu (player stats, camera, visuals, scene inspector, etc.)
- The toggle key can be rebound inside the menu under **System**

### Fixes and New Features:

- Player mesh matches checkpoints and game type
- Player footstep sounds are traced to the first texture, not to a collision + trace from each foot, not from center of the mesh

---

## Multiplayer: Server & Client

OpenOL supports two ways to host a game:

- **Embedded relay** — host from inside the game: open **Multiplayer -> Start Server**. Clients connect via Steam P2P — no open ports or public IP needed. Room code: `DEFAULT`.
- **Standalone relay** — run `OpenOL_Relay` (TUI) or `OpenOL_Relay_GUI` (GUI) on any machine with a reachable IP. Clients connect directly over UDP. Default room code: `PUBLIC`.

To connect to an embedded relay, the host invites friends via Steam — the client accepts the invite and joins automatically. To connect to a standalone relay, use **Multiplayer -> Connect** with the server IP:port and room code.

-> [Full server & client guide](./docs/MULTIPLAYER.md)

---

## Building

### Linux

All compilation runs through `build_wine.sh` (Wine + MSVC 2012). The easiest way to set up the environment is the automated script:

```sh
# Set your desired Wine prefix path, then run:
WINEPREFIX=/path/to/prefix ./Development/Src/Targets/setup_wineprefix.sh
```

This downloads VS 2012 and DirectX SDK automatically and sets up the full build environment. Then:

```sh
cd Development/Src/Targets
./build_wine.sh   # interactive menu with all build steps
```

-> [Full Linux setup & troubleshooting](./docs/LINUX.md) · [All build steps](./docs/BUILD.md)

### Windows

1. Install [Visual Studio 2012](https://archive.org/details/en_visual_studio_professional_2012_x86_dvd) and [DirectX SDK (June 2010)](https://download.microsoft.com/download/A/E/7/AE743F1F-632B-4809-87A9-AA1BB3458E31/DXSDK_Jun10.exe)
2. Open the solution, set configuration to **Release | Mixed Platforms**, build

-> [Full build guide](./docs/BUILD.md)

---

## Packaging

To produce a ready-to-ship `OpenOL.7z`:

```sh
./Development/Src/Targets/publish_production.sh
```

Output is placed in `PublishTemp/`. Users can drag-and-drop the archive contents into their Steam game folder.

-> [Release archive layout](./docs/PACKAGING.md)
