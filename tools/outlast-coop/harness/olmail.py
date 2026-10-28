"""Host side of the patch's data area (see exe-patch/sites.json "layout"): read the counters and set the kill switch of a running client.

  python -I olmail.py <pid> [<pid> ...]                 print the data area of each client
  python -I olmail.py <pid> disable one_owner|triggers|late|none   set a kill switch (a twin without swapping exes): the one-owner rule, the trigger distance rule or the late-copy rule
  python -I olmail.py <pid> radius <units>             set the trigger distance rule's radius (0 = the default 3000)
  python -I olmail.py <pid> load <checkpoint> [<persistent level>]   load a checkpoint through the patch's mailbox (no mouse, no overlay)

The area is part of the patched exe's own section (writable); only these few u32 fields are ever written, from outside, by this tool.
"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import census

CFG = None
for cand in (os.path.join(HERE, "..", "nativepatch", "olfix.json"), os.path.join(HERE, "..", "exe-patch", "olfix.json")):
    if os.path.exists(cand):
        CFG = json.load(open(cand))
        break
if CFG is None:
    sys.exit("olfix.json not found next to the harness")
CAVE, OFF, LAY = int(CFG["section"]["cave_rva"], 16), int(CFG["section"]["data_offset"], 16), CFG["layout"]
MAGIC = 0x5846504F


def read(pid):
    p = census.Proc(pid)
    raw = p.rd(p.base + CAVE + OFF, int(CFG["section"]["data_size"]))
    if raw is None:
        return {"pid": pid, "error": "data area not readable (not the patched exe?)"}
    f = {k: struct.unpack_from("<I", raw, v)[0] for k, v in LAY.items() if v + 4 <= len(raw)}
    f["pid"] = pid
    f["hooks_ran"] = f["magic"] == MAGIC
    return f


def set_disable(pid, mask):
    p = census.Proc(pid, write=True)
    return p.wr(p.base + CAVE + OFF + LAY["disable"], struct.pack("<I", mask))


def set_radius(pid, units):
    """The trigger distance rule's radius (exe-patch v6), stored squared as f32 bits; 0 restores the default."""
    p = census.Proc(pid, write=True)
    bits = 0 if units <= 0 else struct.unpack("<I", struct.pack("<f", float(units) * float(units)))[0]
    return p.wr(p.base + CAVE + OFF + LAY["trig_radius_sq"], struct.pack("<I", bits))


def send_load(pid, name, persist="", timeout=15.0):
    """Ask the patched game to load a checkpoint (the overlay's loader, run from a per-frame hook). Returns (res_code, seconds) or (None, seconds) on a timeout.
    The test writes the argument first and cmd_seq last; the game answers by copying cmd_seq to res_seq."""
    import time
    p = census.Proc(pid, write=True)
    base = p.base + CAVE + OFF
    raw = p.rd(base, 0x100)
    if raw is None:
        raise OSError("data area not readable (not the patched exe?)")
    res_seq = struct.unpack_from("<I", raw, LAY["res_seq"])[0]
    arg = name.encode("ascii") + b"\x00" + persist.encode("ascii") + b"\x00"
    if len(arg) > 255 or len(name) > 127 or len(persist) > 127:
        raise ValueError("name or persistent level name too long")
    ok = p.wr(base + LAY["cmd_arg"], arg + b"\x00") and p.wr(base + LAY["cmd_arg_len"], struct.pack("<I", len(arg))) and p.wr(base + LAY["cmd"], struct.pack("<I", 1))
    if not ok:
        raise OSError("write failed")
    seq = (res_seq + 1) & 0xFFFFFFFF
    t0 = time.time()
    p.wr(base + LAY["cmd_seq"], struct.pack("<I", seq))
    while time.time() - t0 < timeout:
        r = p.rd(base + LAY["res_seq"], 8)
        if r and struct.unpack_from("<I", r, 0)[0] == seq:
            return struct.unpack_from("<i", r, 4)[0], time.time() - t0
        time.sleep(0.05)
    return None, time.time() - t0


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 3 and a[1] == "load":
        print(send_load(int(a[0]), a[2], a[3] if len(a) > 3 else ""))
    elif len(a) == 3 and a[1] == "disable":
        ok = set_disable(int(a[0]), {"one_owner": 1, "triggers": 8, "late": 16, "none": 0}[a[2]])
        print("written" if ok else "write failed")
    elif len(a) == 3 and a[1] == "radius":
        print("written" if set_radius(int(a[0]), float(a[2])) else "write failed")
    else:
        for pid in map(int, a):
            print(json.dumps(read(pid)))
