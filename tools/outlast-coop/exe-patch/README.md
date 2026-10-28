# Native patch: one owner for every map enemy

For `OLGame.exe` of **OpenOL 2.1.0** on Outlast Steam build 576074 (SHA-256 `2e58afbb1203d04476581f34216428d1dfc96228e5f3df8c6881323c56c93346`).
It fixes problem 5 of the write-up: map enemies are duplicated and both copies attack the same player.

## What it changes

Every client runs the AI of each map-placed enemy and sends it; every client turns what it receives into a puppet (OpenOL `EnemyChannel.cpp`,
`TickSend` and `ApplySpawn`). The patch adds one rule: when two copies of one enemy meet (same class, within 150 units), the copy of the client with
the lower player id stays real; the other client destroys its own copy and keeps the puppet. Enemies that exist on one client only are not touched.

Two call sites in the exe are redirected to `olfix.c` (about 1 KB of position independent code in a new section `.olfix`):

| Site (RVA) | Original | Hook | Rule |
|---|---|---|---|
| `0x172B0B4` in `UEnemyChannel::OnBinaryPacket` | `call ApplySpawn` | `my_ApplySpawn` | after the puppet is made: our enemy of that class is at its place -> sender id lower: destroy ours; higher: destroy the puppet |
| `0x1736CAB` in `UEnemyChannel::TickSend` | `call [rax+0x268]` (`SendSpawn`) | `my_SendSpawn` | before announcing our enemy: a puppet of that class is at its place -> owner id lower: destroy ours, announce nothing; higher: destroy the puppet |

Addresses and field offsets were found with Ghidra 12.1.4 (scripts in `ghidra/`) from the strings and the structure of OpenOL's own public
multiplayer source; no Outlast source was used. The code reads the image base from the PEB, so ASLR does not matter, and it has no imports.

## Use

```
python -I build.py                                   # optional: rebuild olfix.json from olfix.c (MinGW gcc); the committed olfix.json is the build used in the tests
python -I apply_patch.py <game copy>\Binaries\Win64\OLGame.exe OLGame_patched.exe
```
`apply_patch.py` never writes to its input and refuses any file with another SHA-256. Keep the original exe; put the patched one in its place in a
**copy** of the game. Every player of a session should use the patched exe (an unpatched client keeps its duplicates on its own side).

## Tests (harness `suite.py`, group A; the suite notices the `.olfix` section and expects the fix)

| Check | Patched exe | Original exe (twin) |
|---|---|---|
| A4 map enemy has one owner (both clients load the checkpoint, lower id first) | PASS | XFAIL, 1 spot with patients sent by both clients |
| A4b the same when the higher id loads first | PASS | XFAIL, 1 spot sent by both |
| A4c both game processes alive after the handover | PASS | PASS |

Not tested yet (see also patch v7 at the end: story enemies born at different times): a scripted story enemy that the story waits for (the destroyed copy may stall a script on the higher-id client), enemies of one class
standing closer than 150 units to each other, three players, two PCs.

## Patch tooling (v2 layout)

- `sites.json` is the one table of what is patched: the input SHA-256, the reference output SHA-256, the new section (name, RVA, size of an optional zeroed data area that makes the
  section writable) and the list of sites (`call32`: a direct call, `call_vt6`: a 6-byte virtual call turned into a direct call plus a nop, `vtable_slot`: an absolute pointer),
  each with the bytes that must be there before it is touched.
- `build.py` compiles `olfix.c` and writes `olfix.json` (code, entry offsets and the table). `apply_patch.py` and `play/apply-native-patch.ps1` both read only `olfix.json`.
- `selftest.py <original OLGame.exe>` is a static test with no game: reference hash, only the allowed bytes changed, every site decodes to its entry, characteristics, and three
  refusals. The two appliers produce identical bytes (checked for the plain section and for the section with a data area).

## Data area, kill switch and counters (patch v2)

The section also carries a zeroed, writable data area (`sites.json` `layout`): a kill switch per feature (bit 0 = the one-owner rule, a SET bit switches it off) and counters (hook calls,
own enemies destroyed as duplicates, puppets destroyed). `harness/olmail.py` reads and sets them from outside with `ReadProcessMemory` and `WriteProcessMemory` on the game's
own process, so a test switches the rule off and on **inside one run** instead of swapping the exe: `harness/twin_live.py` does it (rule on: one enemy in total, the merge counters
move; rule off: every client has its own copy and a puppet, the original bug). Measured 2026-10-22: rule on `own [1, 0] puppets [0, 1]`, rule off `own [1, 1] puppets [1, 1]`.

## Command mailbox (patch v3)

A per-frame hook (`AOLPlayerController::Tick`, the vtable slot +0x350 of the OLPlayerController and MultiplayerController tables, both covered by base relocations) runs commands that a test
writes into the data area: `LOAD_CHECKPOINT name [persistent level]` calls the overlay's own loader (`ExecCP`) from the game thread, outside the network poll. `harness/olmail.py <pid> load <name>` sends it;
`harness/mailbox_live.py` checks it with two clients and **no mouse and no keyboard**: both heroes moved from (3702, 4291) to the survey position of `Prison_IsolationCells01_Mid` (1979, 3481), the mailbox
answered in 0.05 s. The same-world case needs no persistent level name; a jump to another map needs it (not yet mapped).

## Shared checkpoint loads (patch v4, v5)

`StartNewGameAtCheckpoint` (vtable +0xa88 of both controller tables) tells the partners about every checkpoint load with a new world packet `WORLD_CHECKPOINT_LOAD` (0x11);
the world packet dispatch (`call [rax+0x298]` in `OnReceiveBinaryData`) stores a partner's load and the per-frame hook runs it through the overlay's loader. An echo guard keeps the
follower from sending the load back; a death restart and Insane mode are not shared. `harness/shared_cp_live.py`: SC1 to SC5 PASS (2026-10-22).

## Story triggers only near the hero (patch v6)

The bug: a trigger touched by one player is force-activated on every client wherever its hero is (problem 4 of the write-up), so a scripted scene can start for a partner on
another floor. The relay patch 0001 only softens it (it filters by the sender's last hero packet, and only on a relay built with it). v6 does it in the clients, with any relay:

| Site (RVA) | Original | Hook | Rule |
|---|---|---|---|
| `0x1734D4E` in the static `SendWorldIntString` (`0x1734c10`; its only caller `0x172e14c` is `OnPawnTouchedTrigger`) | `call FMpConnection::SendBinary` | `my_SendTrigger` | append a 16-byte tail to `WORLD_TRIGGER_ACT`: magic `OLP1` and where our hero stands |
| `0x172E76C` (already hooked by v5) | `call [rax+0x298]` | `my_WorldPacket` | a trigger whose tail is farther than the radius (default 3000 units) from our hero is queued instead of applied |
| `AOLPlayerController::Tick` (already hooked by v3) | | `my_Tick` | records our hero position every frame; applies the queued triggers we have come within the radius of |

Fail open everywhere: a trigger without the tail (an unpatched partner), a client without a hero of its own, a full queue (6 entries) or a path longer than 155 bytes is applied at once,
as before. Unpatched clients ignore the tail (`ReadWorldString` reads the length byte; trailing bytes are not looked at; the relays log and forward the packet unchanged). The queue is
dropped on every checkpoint load and when another controller starts ticking (a map change), so a channel pointer of an old map is never used. Kill switch: disable bit 3 applies every
trigger at once and flushes the queue. `harness/olmail.py <pid> radius <units>` changes the radius at run time.

Tests:

- `emutest.py` (no game, no exe; needs `pip install unicorn`): runs the built code of `olfix.json` in a CPU emulator against fake controllers, heroes and channels, with the Windows x64
  calling convention. E0 to E17: position recorded, tail appended to triggers only, near applied, far queued and replayed once when near (original sender, type and payload without
  the tail), twin with the bit set, cleared by a checkpoint load and by a new controller, overflow fails open, no hero fails open, other world packets and the v5 checkpoint packet
  untouched. 18/18 PASS; a mutant whose distance check always says "near" fails 8 of them.
- `harness/trigger_near_live.py` (two real clients, a scripted peer, the upstream relay): TN1 to TN6. **Not run yet.**

Limits: the position is where the sender stood when it touched the trigger, not the trigger volume itself (a very large volume needs a larger radius). Two players who both pass
a one-shot trigger each fire it themselves; the queued copy then finds it used up and does nothing (the original `MaxTriggerCount` check).

## Late copies of story enemies (patch v7)

The gap in the one-owner rule: it only merges two copies that stand within 150 units of each other. Map enemies are loaded by both clients at the same
place, so that works. Story enemies (Chris Walker, the chase scenes) are spawned by each client's own Kismet when **that** client's player reaches the
trigger, so the two copies can be born seconds or minutes apart; with v6 the partner's copy of a far trigger even waits until the partner is near on purpose.
By then the first copy has run off after a player, the second one is born at the spawn point, they are more than 150 units apart and both stay: two Walkers,
until (if ever) they happen to walk within 150 units of each other.

The rule added: `my_ApplySpawn` remembers where every puppet was born (the position in its spawn packet, `pup_table`), and `my_SendSpawn` remembers which of our
own enemies it has seen (`seen_table`). An enemy of ours that `my_SendSpawn` sees for the **first** time, of the same class as a live puppet and within 150 units
of that puppet's birth place, is the late copy of the partner's enemy: it is destroyed before it is announced, whatever the player ids (the partner's copy is
already playing the scene, so it stays). Both tables are dropped on every checkpoint load and on a new controller; a table that stays full after dropping gone
entries leaves that enemy to the old rule only (`cnt_late_full`). Kill switch: `disable` bit 4 (`harness/olmail.py <pid> disable late`); bit 0 switches it off too.
Counter: `cnt_late_dropped`.

Limits: the late client's Kismet loses its own copy, the same risk as the v1 rule (a script that waits for that enemy may stall there; not seen yet, not tested
in-game). Two **different** enemies of one class born at the same spot while the first is still alive on the partner's side would be merged by mistake.
An enemy whose spawn packet was a re-announcement (after a load race) has its current position, not its birth place, as "birth place": that pair falls back to
the old rule.

Tests: `emutest.py` L0 to L10 (game-free): v1 regression, the late copy dropped even with the lower id, the puppet kept, a seen enemy walking past the birth
place kept, another class kept, a new enemy elsewhere kept, twins with bit 4 and bit 0 set (the duplicate comes back), a gone puppet no longer counts,
checkpoint load clears, a full table makes room. 29/29 PASS together with E0 to E17. `selftest.py` on the real OpenOL 2.1.0 exe 21/21 PASS, output SHA-256
`52392a32...`. **Not tested in-game yet**: watch `cnt_late_dropped` with `olmail.py` during a Walker scene where one player arrives a while after the other.

