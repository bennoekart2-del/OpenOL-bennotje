"""Game-free test of the trigger hooks (patch v6) and the enemy hooks (one owner, late copies of patch v7) of olfix.c: runs the built code of olfix.json in a CPU emulator against fake game objects.

  pip install unicorn
  python -I emutest.py            prints one RESULT line per check and a SUMMARY; exit code 0 only when every check passes

No OLGame.exe is needed: the code blob is position independent and reaches the game only through the image base (read from a fake PEB) plus the RVAs
in olfix.c. Every game function it calls is a stub here that records its arguments. What it proves: the packet layout, the distance rule, the queue,
its replay and its clearing, with the Windows x64 calling convention. What it cannot prove: that the offsets match the real game (that needs the
in-game test in README.md).
"""
import json, os, struct, sys
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_RSP, UC_X86_REG_RIP,
                               UC_X86_REG_GS_BASE, UC_X86_REG_XMM1)

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "olfix.json")))
LAY = CFG["layout"]
IB = 0x140000000
CAVE = int(CFG["section"]["cave_rva"], 16)
DATA = IB + CAVE + int(CFG["section"]["data_offset"], 16)

RVA = dict(sendbinary=0x174d9b0, tick=0x174f1d0, sngac=0x174e830, execcp=0x1707020, getgameinfo=0x0d214c0, applyspawn=0x171eb00, destroyactor=0x08d7550)
LOCALPLAYERID, SYNCENEMIES = 0x36b9a70, 0x36b9aec
CH_CONTROLLER, CTRL_CACHED, CTRL_REMOTE, REMOTE_STRIDE, REMOTE_DUMMY, REMOTE_OWNER, OBJ_CLASS = 0x60, 0xe78, 0xeb8, 0x44, 0x10, 0x18, 0x50
PC_HEROPAWN, ACTOR_LOC, PAWN_HEALTH = 0xa5c, 0x80, 0x37c
CH_WORLD, TRIGGER_ACT, CHECKPOINT_LOAD = 5, 0x01, 0x11
DISABLE_TRIGGER_NEAR = 8
DISABLE_ONE_OWNER, DISABLE_LATE_COPY = 1, 16

PEB, HEAP, STACK, DONE, ORIG_WORLD, ORIG_SENDSPAWN = 0x10000, 0x200000, 0x800000, 0x30000, 0x31000, 0x31100


class Machine:
    def __init__(self):
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_64)
        mu.mem_map(PEB, 0x1000)
        mu.mem_map(DONE, 0x2000)
        mu.mem_map(HEAP, 0x100000)
        mu.mem_map(STACK - 0x10000, 0x20000)
        img_end = CAVE + int(CFG["section"]["data_offset"], 16) + CFG["section"]["data_size"]
        mu.mem_map(IB, (img_end + 0xfff) & ~0xfff)               # sparse image: only the stubs and the .olfix section are filled in
        mu.mem_write(PEB + 0x10, struct.pack("<Q", IB))
        self.gs = 0x20000                                          # a fake TEB: gs:0x60 holds the PEB pointer
        mu.mem_map(self.gs, 0x1000)
        mu.mem_write(self.gs + 0x60, struct.pack("<Q", PEB))
        mu.reg_write(UC_X86_REG_GS_BASE, self.gs)
        mu.mem_write(IB + CAVE, bytes.fromhex(CFG["hex"]))
        area = bytearray(CFG["section"]["data_size"])
        init = CFG.get("data_init")
        if init:
            blob = b"".join(p.encode() + b"\0" + v.encode() + b"\0" for p, v in init["pairs"]) + b"\0"
            area[LAY[init["field"]]:LAY[init["field"]] + len(blob)] = blob
        mu.mem_write(DATA, bytes(area))
        self.calls = []
        self.stubs = {IB + RVA["sendbinary"]: "sendbinary", IB + RVA["tick"]: "tick", IB + RVA["sngac"]: "sngac",
                      IB + RVA["execcp"]: "execcp", IB + RVA["getgameinfo"]: "getgameinfo", ORIG_WORLD: "orig_world",
                      IB + RVA["applyspawn"]: "applyspawn", IB + RVA["destroyactor"]: "destroyactor", ORIG_SENDSPAWN: "orig_sendspawn"}
        for a in self.stubs:
            mu.mem_write(a, b"\x31\xc0\xc3")                        # xor eax, eax; ret
        for a in self.stubs:
            mu.hook_add(UC_HOOK_CODE, self._stub, begin=a, end=a)
        self.next_puppet = None                                    # what the fake ApplySpawn makes: (controller, puppet, owner id)
        self.brk = HEAP

    def _stub(self, mu, addr, size, _):
        r = lambda reg: mu.reg_read(reg)
        name = self.stubs[addr]
        if name == "sendbinary":
            self.calls.append((name, bytes(mu.mem_read(r(UC_X86_REG_RDX), r(UC_X86_REG_R8)))))
        elif name == "orig_world":
            rsp = r(UC_X86_REG_RSP)
            n = struct.unpack("<i", mu.mem_read(rsp + 0x28, 4))[0]
            self.calls.append((name, r(UC_X86_REG_RCX), r(UC_X86_REG_RDX) & 0xffffffff, r(UC_X86_REG_R8) & 0xffffffff,
                               bytes(mu.mem_read(r(UC_X86_REG_R9), n)) if n > 0 else b""))
        elif name == "applyspawn":
            ctrl, pup, owner = self.next_puppet
            n = struct.unpack("<i", mu.mem_read(ctrl + CTRL_REMOTE + 8, 4))[0]
            rem = struct.unpack("<Q", mu.mem_read(ctrl + CTRL_REMOTE, 8))[0]
            r = rem + n * REMOTE_STRIDE
            mu.mem_write(r + REMOTE_DUMMY, struct.pack("<Q", pup))
            mu.mem_write(r + REMOTE_OWNER, struct.pack("<i", owner))
            mu.mem_write(ctrl + CTRL_REMOTE + 8, struct.pack("<i", n + 1))
            self.calls.append((name, pup))
        elif name == "destroyactor":
            self.calls.append((name, r(UC_X86_REG_RDX)))
        elif name == "orig_sendspawn":
            self.calls.append((name, r(UC_X86_REG_RDX)))
        else:
            self.calls.append((name,))

    def alloc(self, n):
        a = self.brk
        self.brk += (n + 0xf) & ~0xf
        return a

    def call(self, symbol, *args, xmm1=None):
        mu = self.mu
        rsp = STACK - 0x100
        regs = [UC_X86_REG_RCX, UC_X86_REG_RDX, UC_X86_REG_R8, UC_X86_REG_R9]
        for i, v in enumerate(args[:4]):
            mu.reg_write(regs[i], v & 0xffffffffffffffff)
        for i, v in enumerate(args[4:]):
            mu.mem_write(rsp + 0x28 + 8 * i, struct.pack("<Q", v & 0xffffffffffffffff))
        if xmm1 is not None:
            mu.reg_write(UC_X86_REG_XMM1, struct.unpack("<I", struct.pack("<f", xmm1))[0])
        mu.mem_write(rsp, struct.pack("<Q", DONE))
        mu.reg_write(UC_X86_REG_RSP, rsp)
        mu.emu_start(IB + CAVE + CFG["entries"][symbol], DONE, count=2_000_000)
        return mu.reg_read(UC_X86_REG_RAX)

    def u32(self, field):
        return struct.unpack("<I", self.mu.mem_read(DATA + LAY[field], 4))[0]

    def set_u32(self, field, v):
        self.mu.mem_write(DATA + LAY[field], struct.pack("<I", v))

    # fake game objects
    def controller(self):
        pc = self.alloc(0x1000)
        hero = self.alloc(0x400)
        self.mu.mem_write(pc + PC_HEROPAWN, struct.pack("<Q", hero))
        self.mu.mem_write(hero + PAWN_HEALTH, struct.pack("<i", 100))
        return pc, hero

    def move(self, hero, x, y, z=0.0):
        self.mu.mem_write(hero + ACTOR_LOC, struct.pack("<fff", x, y, z))

    def channel(self):
        vt = self.alloc(0x400)
        self.mu.mem_write(vt + 0x298, struct.pack("<Q", ORIG_WORLD))
        ch = self.alloc(0x100)
        self.mu.mem_write(ch, struct.pack("<Q", vt))
        return ch

    # enemies: a multiplayer controller with CachedEnemies / RemoteEnemies, an enemy channel whose vtable +0x268 is the original SendSpawn
    def enemy_world(self, my_id):
        self.mu.mem_write(IB + LOCALPLAYERID, struct.pack("<i", my_id))
        self.mu.mem_write(IB + SYNCENEMIES, struct.pack("<i", 1))
        ctrl = self.alloc(0x1000)
        self.mu.mem_write(ctrl + CTRL_CACHED, struct.pack("<Qi", self.alloc(8 * 128), 0))
        self.mu.mem_write(ctrl + CTRL_REMOTE, struct.pack("<Qi", self.alloc(REMOTE_STRIDE * 128), 0))
        vt = self.alloc(0x400)
        self.mu.mem_write(vt + 0x268, struct.pack("<Q", ORIG_SENDSPAWN))
        ch = self.alloc(0x100)
        self.mu.mem_write(ch, struct.pack("<Q", vt))
        self.mu.mem_write(ch + CH_CONTROLLER, struct.pack("<Q", ctrl))
        return ctrl, ch

    def enemy(self, cls, x, y, z=0.0, own_ctrl=None):
        e = self.alloc(0x400)
        self.mu.mem_write(e + OBJ_CLASS, struct.pack("<Q", cls))
        self.mu.mem_write(e + PAWN_HEALTH, struct.pack("<i", 100))
        self.move(e, x, y, z)
        if own_ctrl:                                               # add to CachedEnemies
            arr, n = struct.unpack("<Qi", self.mu.mem_read(own_ctrl + CTRL_CACHED, 12))
            self.mu.mem_write(arr + 8 * n, struct.pack("<Q", e))
            self.mu.mem_write(own_ctrl + CTRL_CACHED + 8, struct.pack("<i", n + 1))
        return e

    def drop_remote(self, ctrl, i):
        """the owner deleted that enemy: its RemoteEnemies entry loses its puppet"""
        rem = struct.unpack("<Q", self.mu.mem_read(ctrl + CTRL_REMOTE, 8))[0]
        self.mu.mem_write(rem + i * REMOTE_STRIDE + REMOTE_DUMMY, struct.pack("<Q", 0))

    def packet(self, payload):
        a = self.alloc(len(payload) + 16)
        self.mu.mem_write(a, payload)
        return a


def trig_payload(path, count=0, pos=None):
    p = struct.pack("<i", count) + bytes([len(path)]) + path.encode()
    if pos is not None:
        p += struct.pack("<I", 0x31504C4F) + struct.pack("<fff", *pos)
    return p


RESULTS = []


def fbits(v):
    return struct.unpack("<I", struct.pack("<f", v))[0]


def spawn_packet(m, ch, ctrl, sender, cls, x, y, z=0.0):
    """a partner's spawn packet: the fake ApplySpawn makes a puppet at (x, y, z); returns the puppet and the calls"""
    pup = m.enemy(cls, x, y, z)
    m.next_puppet = (ctrl, pup, sender)
    m.calls.clear()
    m.call("my_ApplySpawn", ch, sender, 0, 0, fbits(x), fbits(y), fbits(z), 0, 0, 0, 0, 0, 0, 0, 0)
    return pup, list(m.calls)


def send(m, ch, e):
    """one TickSend step for our enemy e: True when it was announced, plus the actors destroyed"""
    m.calls.clear()
    m.call("my_SendSpawn", ch, e)
    return any(c[0] == "orig_sendspawn" and c[1] == e for c in m.calls), [c[1] for c in m.calls if c[0] == "destroyactor"]


def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"RESULT {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)


def world(m, ch, sender, payload, type_=TRIGGER_ACT):
    a = m.packet(payload)
    m.calls.clear()
    m.call("my_WorldPacket", ch, sender, type_, a, len(payload))
    return [c for c in m.calls if c[0] == "orig_world"]


def tick(m, pc):
    m.calls.clear()
    m.call("my_Tick", pc, 0, 0, xmm1=0.016)
    return [c for c in m.calls if c[0] == "orig_world"]


def main():
    m = Machine()
    pc, hero = m.controller()
    ch = m.channel()
    m.move(hero, 100.0, 200.0, 50.0)
    tick(m, pc)
    check("E0 the per-frame hook records our hero", m.u32("hero_valid") == 1 and struct.unpack("<f", struct.pack("<I", m.u32("hero_x")))[0] == 100.0)

    # sender side
    path = "TheWorld:PersistentLevel.Main_Sequence.SeqEvent_Touch_7"
    body = bytes([CH_WORLD, TRIGGER_ACT]) + trig_payload(path, 3)
    m.calls.clear()
    m.call("my_SendTrigger", 0x1234, m.packet(body), len(body))
    sent = [c[1] for c in m.calls if c[0] == "sendbinary"]
    check("E1 a trigger is sent with our position appended", len(sent) == 1 and sent[0][:len(body)] == body and sent[0][len(body):] == struct.pack("<I", 0x31504C4F) + struct.pack("<fff", 100.0, 200.0, 50.0),
          f"len {len(sent[0]) if sent else None} (was {len(body)})")
    other = bytes([CH_WORLD, 0x07, 1, 2, 3])
    m.calls.clear()
    m.call("my_SendTrigger", 0x1234, m.packet(other), len(other))
    sent = [c[1] for c in m.calls if c[0] == "sendbinary"]
    check("E2 any other packet is sent unchanged", sent == [other])

    # receiver side
    near = world(m, ch, 1001, trig_payload(path, 3, (300.0, 200.0, 50.0)))
    check("E3 a trigger touched near us is applied at once", len(near) == 1 and near[0][2] == 1001 and near[0][3] == TRIGGER_ACT)
    plain = world(m, ch, 1001, trig_payload(path, 3))
    check("E4 a trigger without position (unpatched sender) is applied at once", len(plain) == 1)
    far_p = trig_payload("Far.SeqEvent_Touch_1", 0, (20000.0, 200.0, 50.0))
    far = world(m, ch, 1002, far_p)
    check("E5 a trigger touched far away is not applied", far == [] and m.u32("trig_count") == 1 and m.u32("cnt_trig_deferred") == 1)
    check("E6 ... nor on the next frames while we stay away", tick(m, pc) == [] and tick(m, pc) == [] and m.u32("trig_count") == 1)
    m.move(hero, 18000.0, 200.0, 50.0)
    rep = tick(m, pc)
    want = trig_payload("Far.SeqEvent_Touch_1", 0)
    check("E7 it is applied once we come within the radius, with the original sender, type and payload (no tail)",
          len(rep) == 1 and rep[0][1] == ch and rep[0][2] == 1002 and rep[0][3] == TRIGGER_ACT and rep[0][4] == want and m.u32("trig_count") == 0,
          f"{rep}")
    check("E8 ... and only once", tick(m, pc) == [] and m.u32("cnt_trig_replayed") == 1)

    # twin: the feature switched off
    m.move(hero, 0.0, 0.0, 0.0)
    world(m, ch, 1002, trig_payload("A.SeqEvent_Touch_2", 0, (50000.0, 0.0, 0.0)))
    m.set_u32("disable", DISABLE_TRIGGER_NEAR)
    off_now = world(m, ch, 1002, trig_payload("B.SeqEvent_Touch_3", 0, (50000.0, 0.0, 0.0)))
    check("E9 twin: with bit 3 set a far trigger is applied at once (upstream behaviour)", len(off_now) == 1)
    flushed = tick(m, pc)
    check("E10 twin: the queue is flushed when the feature is switched off", len(flushed) == 1 and m.u32("trig_count") == 0)
    m.set_u32("disable", 0)

    # clearing
    world(m, ch, 1002, trig_payload("C.SeqEvent_Touch_4", 0, (50000.0, 0.0, 0.0)))
    fname = m.alloc(16)
    name = "Prison_ToPrisonFloor".encode("utf-16-le") + b"\0\0"
    s = m.alloc(len(name))
    m.mu.mem_write(s, name)
    m.mu.mem_write(fname, struct.pack("<Qii", s, len(name) // 2, len(name) // 2))
    m.call("my_SNGAC", pc, fname, 0)
    check("E11 a checkpoint load drops the queue", m.u32("trig_count") == 0 and m.u32("cnt_trig_cleared") >= 1)
    world(m, ch, 1002, trig_payload("D.SeqEvent_Touch_5", 0, (50000.0, 0.0, 0.0)))
    pc2, hero2 = m.controller()
    m.move(hero2, 50000.0, 0.0, 0.0)
    rep = tick(m, pc2)
    check("E12 a new controller (map change) drops the queue instead of replaying it", rep == [] and m.u32("trig_count") == 0)
    pc, hero = pc2, hero2

    # overflow fails open
    m.move(hero, 0.0, 0.0, 0.0)
    tick(m, pc)
    applied = sum(len(world(m, ch, 1002, trig_payload(f"E.SeqEvent_Touch_{i}", 0, (50000.0, 0.0, 0.0)))) for i in range(7))
    check("E13 a full queue (6) applies the 7th far trigger at once", m.u32("trig_count") == 6 and applied == 1 and m.u32("cnt_trig_overflow") == 1)
    m.move(hero, 50000.0, 0.0, 0.0)
    rep = tick(m, pc)
    check("E14 all six are applied in arrival order when we get there", [c[4][5:] for c in rep] == [f"E.SeqEvent_Touch_{i}".encode() for i in range(6)])

    # the hero is unknown: fail open
    m.mu.mem_write(pc + PC_HEROPAWN, struct.pack("<Q", 0))
    tick(m, pc)
    unk = world(m, ch, 1002, trig_payload("F.SeqEvent_Touch_9", 0, (90000.0, 0.0, 0.0)))
    check("E15 without a hero of our own a far trigger is applied at once", len(unk) == 1 and m.u32("hero_valid") == 0)

    # other world packets are untouched; the checkpoint packet still goes to the follow mailbox
    other = world(m, ch, 1002, bytes([1, 2, 3]), type_=0x07)
    check("E16 other world packets go to the original handler", len(other) == 1 and other[0][3] == 0x07)
    cp = world(m, ch, 1002, bytes([4]) + b"Lab_" + bytes([0]), type_=CHECKPOINT_LOAD)
    check("E17 the checkpoint packet (v5) still goes to the follow mailbox", cp == [] and m.u32("follow_pending") == 1)

    enemy_checks()

    n_ok = sum(RESULTS)
    print(f"SUMMARY {n_ok}/{len(RESULTS)} PASS")
    sys.exit(0 if n_ok == len(RESULTS) else 1)


def enemy_checks():
    """L0 to L9: the one-owner rule and the late-copy rule (patch v7). We are player 2, the partner is player 1 (lower) or 3 (higher)."""
    m = Machine()
    ctrl, ch = m.enemy_world(2)
    WALKER, PATIENT = 0x7000, 0x7100                               # two fake class pointers
    S = (1000.0, 2000.0, 0.0)                                      # a spawn point of the story

    # regression: the same-place rule of v1 (both copies born at the same moment)
    own = m.enemy(WALKER, *S, own_ctrl=ctrl)
    pup, _ = spawn_packet(m, ch, ctrl, 1, WALKER, *S)
    ann, gone = send(m, ch, own)
    check("L0 same place, lower owner: our copy is destroyed and not announced (v1 rule)", not ann and own in gone, f"{gone}")
    m.drop_remote(ctrl, 0)

    # the bug: the partner's copy was born at S long ago and has walked away; ours is born now at S
    m.call("my_SNGAC", 0, 0, 0)                                    # a fresh world (also clears the late tables)
    ctrl, ch = m.enemy_world(2)
    pup, _ = spawn_packet(m, ch, ctrl, 3, WALKER, *S)              # partner (HIGHER id) announced its Walker at S
    m.move(pup, 9000.0, 2000.0, 0.0)                               # ... and it chased them 80 m away
    late = m.enemy(WALKER, *S, own_ctrl=ctrl)                      # our Kismet now spawns our own Walker at S
    ann, gone = send(m, ch, late)
    check("L1 a new enemy of ours born where a partner's copy was born is destroyed before it is announced (even though our id is lower)",
          not ann and gone == [late] and m.u32("cnt_late_dropped") == 1, f"ann {ann} gone {gone}")
    check("L2 ... and the partner's puppet is kept", pup not in gone)

    old = m.enemy(WALKER, 5000.0, 5000.0, own_ctrl=ctrl)
    ann1, _ = send(m, ch, old)
    m.move(old, *S)
    ann2, gone = send(m, ch, old)
    check("L3 an enemy of ours seen before that walks past that birth place is kept", ann1 and ann2 and gone == [], f"{gone}")

    other = m.enemy(PATIENT, *S, own_ctrl=ctrl)
    ann, gone = send(m, ch, other)
    check("L4 a new enemy of another class at that birth place is kept", ann and gone == [])

    fresh = m.enemy(WALKER, -7000.0, 0.0, own_ctrl=ctrl)
    ann, gone = send(m, ch, fresh)
    check("L5 a new enemy born elsewhere is kept", ann and gone == [])

    m.set_u32("disable", DISABLE_LATE_COPY)
    late2 = m.enemy(WALKER, *S, own_ctrl=ctrl)
    ann, gone = send(m, ch, late2)
    check("L6 twin: with bit 4 set the late copy is kept (v6 behaviour, the duplicate)", ann and gone == [])
    m.set_u32("disable", DISABLE_ONE_OWNER)
    late3 = m.enemy(WALKER, *S, own_ctrl=ctrl)
    ann, gone = send(m, ch, late3)
    check("L7 bit 0 (the whole one-owner rule off) also switches the late rule off", ann and gone == [])
    m.set_u32("disable", 0)

    m.drop_remote(ctrl, 0)                                         # the partner's Walker died / was deleted
    late4 = m.enemy(WALKER, *S, own_ctrl=ctrl)
    ann, gone = send(m, ch, late4)
    check("L8 once the partner's copy is gone, a new enemy at its birth place is kept", ann and gone == [])

    pup2, _ = spawn_packet(m, ch, ctrl, 3, PATIENT, -3000.0, 0.0)
    m.move(pup2, 0.0, 0.0, 0.0)
    m.call("my_SNGAC", 0, 0, 0)
    check("L9 a checkpoint load drops both tables", m.u32("pup_count") == 0 and m.u32("seen_count") == 0)

    # full tables: gone puppets are dropped to make room
    m2 = Machine()
    c2, h2 = m2.enemy_world(2)
    for i in range(32):
        spawn_packet(m2, h2, c2, 3, PATIENT, 100.0 * i, 50000.0)
    for i in range(32):
        m2.drop_remote(c2, i)
    pw, _ = spawn_packet(m2, h2, c2, 3, WALKER, *S)
    m2.move(pw, 9000.0, 0.0, 0.0)
    e2 = m2.enemy(WALKER, *S, own_ctrl=c2)
    ann, gone = send(m2, h2, e2)
    check("L10 a full birth-place table makes room by dropping gone puppets", not ann and gone == [e2] and m2.u32("pup_count") == 1, f"count {m2.u32('pup_count')}")


if __name__ == "__main__":
    main()
