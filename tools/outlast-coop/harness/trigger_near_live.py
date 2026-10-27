"""Story triggers only for players near them (exe-patch v6), with two real clients: a trigger from far away waits until the hero comes near.

  python -I trigger_near_live.py        two clients on the patched exe, a scripted peer sends the triggers (no mouse and no keyboard after the launch)

Checks
  TN1  a trigger sent with a position next to the players fires on both clients at once
  TN2  the same trigger sent with a position 50000 units away fires on neither client, and each client has it queued (counters)
  TN3  coming near (here: the radius is widened through the data area instead of walking) applies the queued trigger on both clients, once
  TN4  twin: with the rule switched off (disable bit 3) a far trigger fires on both clients at once, as upstream does
  TN5  a trigger without a position (an unpatched sender) fires on both clients at once
  TN6  both processes alive
Uses the repeatable trigger of suite group B (Admin_Explosion, SeqEvent_Touch_3) and waits between sends, because a repeatable trigger is dropped
while its Kismet chain is still playing. The relay is the upstream one (no --trigger-radius), so all filtering is done by the clients.
"""
import os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ol, olmail

PY = [sys.executable, "-I"]
DISABLE_SHARED_CP, DISABLE_TRIGGERS = 4, 8
PATH = "center_block_sript.TheWorld:PersistentLevel.Main_Sequence.SeqEvent_Touch_3"
MARKER = re.escape("ForceActivateTouchEvent: SeqEvent_Touch_3 ")
CHAIN_WAIT = 8


def fired(c):
    try:
        return len(re.findall(MARKER, open(c["log"], encoding="utf-8", errors="replace").read()))
    except OSError:
        return 0


def send(pos=None):
    args = ["trigger", PATH] if pos is None else ["trigger-tail", PATH, *map(str, pos)]
    r = subprocess.run(PY + [os.path.join(HERE, "fake_peer.py"), "127.0.0.1", "17778", "PUBLIC", *args], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def case(cs, pos, settle=5):
    before = [fired(c) for c in cs]
    ok = send(pos)
    time.sleep(settle)
    return ok, [fired(c) - b for c, b in zip(cs, before)]


def counters(c):
    d = olmail.read(c["pid"])
    return {k: d.get(k) for k in ("trig_count", "cnt_trig_recv", "cnt_trig_deferred", "cnt_trig_replayed", "cnt_trig_cleared", "hero_valid")}


def result(name, ok, detail):
    print(f"RESULT {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)
    return ok


def main():
    ol.up()
    ol.launch(2, "prison_persistent")   # adminblock_persistent as a start map crashes (UnWorld.cpp:1693); jump by checkpoint
    cs = ol.clients()
    time.sleep(20)
    for c in cs:                          # each client loads the checkpoint itself; shared loads (v5) are off during the setup
        olmail.set_disable(c["pid"], DISABLE_SHARED_CP)
        olmail.set_radius(c["pid"], 0)
    for i in range(len(cs)):
        ol.cp(i, "Admin_Explosion")
    time.sleep(5)
    for c in cs:
        olmail.set_disable(c["pid"], 0)
    h = ol.read_state()["heroes"].get(str(cs[0]["port"]))
    if not h:
        sys.exit("no hero state from the proxy")
    here, far = (h["x"], h["y"], h["z"]), (h["x"] + 50000, h["y"], h["z"])

    ok, f = case(cs, here)
    result("TN1.near-trigger-fires-on-both", ok and all(n >= 1 for n in f), f"fired {f}")
    time.sleep(CHAIN_WAIT)

    ok, f = case(cs, far)
    k = [counters(c) for c in cs]
    result("TN2.far-trigger-waits", ok and all(n == 0 for n in f) and all(x["trig_count"] == 1 for x in k), f"fired {f}, counters {k}")

    before = [fired(c) for c in cs]
    for c in cs:
        olmail.set_radius(c["pid"], 60000)  # the hero 'comes near': the queued trigger is now inside the radius
    time.sleep(5)
    f = [fired(c) - b for c, b in zip(cs, before)]
    k2 = [counters(c) for c in cs]
    applied = [x["cnt_trig_replayed"] - y["cnt_trig_replayed"] for x, y in zip(k2, k)]
    result("TN3.queued-trigger-applied-when-near", all(a == 1 for a in applied) and all(n >= 1 for n in f) and all(x["trig_count"] == 0 for x in k2),
           f"replayed {applied}, fired {f}, counters {k2}")
    for c in cs:
        olmail.set_radius(c["pid"], 0)
    time.sleep(CHAIN_WAIT)

    for c in cs:
        olmail.set_disable(c["pid"], DISABLE_TRIGGERS)
    ok, f = case(cs, far)
    result("TN4.twin-rule-off-far-trigger-fires-on-both", ok and all(n >= 1 for n in f), f"fired {f}")
    for c in cs:
        olmail.set_disable(c["pid"], 0)
    time.sleep(CHAIN_WAIT)

    ok, f = case(cs, None)
    result("TN5.trigger-without-position-fires-on-both", ok and all(n >= 1 for n in f), f"fired {f}")

    alive = [ol.window_rect(c["pid"]) is not None for c in cs]
    result("TN6.both-clients-alive", all(alive), f"{alive}")
    print("final counters", [counters(c) for c in cs], flush=True)
    ol.down()


if __name__ == "__main__":
    main()
