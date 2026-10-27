"""Scripted OpenOL 2.1.0 peer: joins a relay room and injects packets, to test the receiving client
without walking a bot through the level.

  python -I fake_peer.py <host> <port> <room> trigger <event_path> [count]
  python -I fake_peer.py <host> <port> <room> door open|close <x> <y> <z>
  python -I fake_peer.py <host> <port> <room> doors-burst <x> <y> <z> <n> <interval_s>
  python -I fake_peer.py <host> <port> <room> push <keyx> <keyy> <keyz> <disp>
  python -I fake_peer.py <host> <port> <room> trigger-at <path> <x> <y> <z> <state.json>
  python -I fake_peer.py <host> <port> <room> enemy-near <dx> <dy> <dz> <hold_s>
  python -I fake_peer.py <host> <port> <room> sweep <level_prefix> <from> <to> <delay_s> <client_log> [out]

sweep sends WORLD_TRIGGER_ACT for
  <level_prefix>.TheWorld:PersistentLevel.Main_Sequence.SeqEvent_Touch_<N>   N = from..to
one at a time, `delay_s` apart, and records the send time of each. At the end it maps the client log's
game-time stamps to wall time (log open time + seconds) and lists, per sent trigger, the log lines that
followed it (KISMET remote events, checkpoint save/load/apply, matinee). Packets received from other peers
(world/enemy/lifecycle) are printed as they arrive.

Wire format (MultiplayerLink.cpp SendBinary): [channel][type][player_id LE4][payload].
WORLD_TRIGGER_ACT payload (WorldChannel.cpp SendWorldIntString): [count LE4][len][utf8 path].
"""
import datetime
import re
import socket
import struct
import sys
import threading
import time

CH_SRV, CH_WORLD = 0x00, 0x05
SRV_HELLO, SRV_PING = 0x01, 0x02
WORLD_TRIGGER_ACT = 0x01
INTERESTING = re.compile(r"\[TA\]|KISMET|CHECKPOINT|[Cc]heckpoint|Interp|Matinee|LoadMap|SNGAC")


class Peer:
    def __init__(self, host, port, room, nick="FakePeer"):
        self.addr = (host, port)
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            self.s.ioctl(socket.SIO_UDP_CONNRESET, False)
        self.s.settimeout(0.5)
        self.pid = None
        self.alive = True
        self.spawns = []       # ENEMY_SPAWN packets received (whole datagrams), for enemy-near
        # Wait up to 6 s for READY, repeating HELLO every 0.5 s. Other packets (ONLINE_COUNT 0xE1 can arrive before READY on a reordering
        # link) must not use up a retry: counting packets instead of time made this give up within a second on an impaired link.
        deadline, last_hello = time.time() + 6.0, 0.0
        while self.pid is None and time.time() < deadline:
            if time.time() - last_hello >= 0.5:
                self.s.sendto(f"HELLO,{room},\n".encode(), self.addr)
                last_hello = time.time()
            try:
                data, _ = self.s.recvfrom(65535)
            except socket.timeout:
                continue
            if data[0] == 0xE0 and len(data) >= 9:  # SRV_READY [E0][pad4][pid LE4]...
                self.pid = struct.unpack_from("<I", data, 5)[0]
            elif data[0] == 0xE2:
                sys.exit(f"HELLO_FAIL: {data[6:].decode('ascii', 'replace')}")
        if self.pid is None:
            sys.exit("no READY from relay")
        n = nick.encode()
        self.send(CH_SRV, SRV_HELLO, bytes([len(n)]) + n)
        print(f"joined room {room} as pid {self.pid}", flush=True)
        threading.Thread(target=self._loop, daemon=True).start()

    def send(self, ch, typ, payload=b""):
        self.s.sendto(bytes([ch, typ]) + struct.pack("<I", self.pid) + payload, self.addr)

    def trigger(self, path, count=0, pos=None):
        """pos=(x, y, z) appends the tail of exe-patch v6 (magic 'OLP1' + where the sender stood), as a patched client sends it."""
        p = path.encode()
        tail = b"" if pos is None else struct.pack("<I", 0x31504C4F) + struct.pack("<fff", *pos)
        self.send(CH_WORLD, WORLD_TRIGGER_ACT, struct.pack("<i", count) + bytes([len(p)]) + p + tail)

    def hero_at(self, template_hex, x, y, z):
        """Announce a hero position: a copy of a real HERO_STATE packet (so receivers parse a full-size one) with our id and x,y,z."""
        d = bytearray.fromhex(template_hex)
        d[2:6] = struct.pack("<I", self.pid)
        d[6:18] = struct.pack("<fff", x, y, z)
        self.s.sendto(bytes(d), self.addr)

    def push(self, key, disp, steps=8):
        """Push the object at `key` (the x,y,z the clients announced in PUSH_INIT) to displacement `disp`: PUSH_STATE with bPushing=1 and
        a rising sequence number, then a stop packet (bPushing=0) with the final displacement. Packet: [CH_PUSH 4][type 1][pid][x,y,z i32][disp*1000 i32][seq u32][bPushing u8]."""
        x, y, z = key
        for i in range(1, steps + 1):
            self.send(4, 1, struct.pack("<iiiiIB", x, y, z, int(disp * 1000 * i / steps), i + 1, 1))
            time.sleep(0.1)
        self.send(4, 1, struct.pack("<iiiiIB", x, y, z, int(disp * 1000), steps + 2, 0))

    def door(self, kind, x, y, z):
        """DOOR_OPEN (4) / DOOR_CLOSE (5): [CH_DOOR][type][pid][X i32][Y i32][Z i32] (DoorChannelPackets.h)."""
        self.send(2, {"open": 4, "close": 5}[kind], struct.pack("<iii", x, y, z))

    def _loop(self):
        next_ping = 0
        while self.alive:
            if time.time() >= next_ping:  # keeps the relay from timing us out (30 s)
                next_ping = time.time() + 5
                self.send(CH_SRV, SRV_PING, struct.pack("<I", int(time.time() * 1000) & 0xFFFFFFFF))
            try:
                data, _ = self.s.recvfrom(65535)
            except (socket.timeout, OSError):
                continue
            if len(data) >= 8 and data[0] == 3 and data[1] == 1:
                self.spawns.append(bytes(data))
            if len(data) >= 2 and data[0] in (3, 5) and data[1] not in (0x0D, 0x04):
                print(f"  rx ch{data[0]} t0x{data[1]:02x} len={len(data)}"
                      f" {data[6:80].decode('ascii', 'replace')!r}", flush=True)


def log_lines_wall(path):
    """Client log lines with game time converted to wall time."""
    text = open(path, encoding="utf-8", errors="replace").read().splitlines()
    start = None
    for line in text[:5]:
        m = re.search(r"Log file open, (\d+)/(\d+)/(\d+) (\d+):(\d+):(\d+)", line)
        if m:
            mo, d, y, hh, mm, ss = map(int, m.groups())
            start = datetime.datetime(2000 + y, mo, d, hh, mm, ss).timestamp()
    out = []
    for line in text:
        m = re.match(r"\[(\d+\.\d+)\]", line)
        if m and start and INTERESTING.search(line):
            out.append((start + float(m.group(1)), line))
    return out


def main():
    host, port, room, cmd = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    peer = Peer(host, port, room)
    if cmd == "trigger":
        peer.trigger(sys.argv[5], int(sys.argv[6]) if len(sys.argv) > 6 else 0)
        print("sent", sys.argv[5], flush=True)
        time.sleep(2)
        return
    if cmd == "trigger-tail":
        # trigger-tail <path> <x> <y> <z>: send the trigger the way a client with exe-patch v6 does (position appended), no hero packet
        pos = (float(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8]))
        peer.trigger(sys.argv[5], 0, pos)
        print("sent", sys.argv[5], "with position", pos, flush=True)
        time.sleep(2)
        return
    if cmd == "trigger-at":
        # trigger-at <path> <x> <y> <z> <state.json>: stand at x,y,z (using a real hero packet from the proxy's state file), then send the trigger
        import json
        path, x, y, z, statef = sys.argv[5], float(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8]), sys.argv[9]
        raw = next(h["raw"] for h in json.load(open(statef, encoding="utf-8"))["heroes"].values() if h.get("raw"))
        for _ in range(4):
            peer.hero_at(raw, x, y, z)
            time.sleep(0.25)
        peer.trigger(path)
        print("sent", path, "from", (x, y, z), flush=True)
        time.sleep(2)
        return
    if cmd == "push":
        peer.push((int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])), float(sys.argv[8]))
        print("pushed", sys.argv[5:9], flush=True)
        time.sleep(1.5)
        return
    if cmd == "doors-burst":
        # doors-burst <x> <y> <z> <n> <interval_s>: alternating DOOR_OPEN / DOOR_CLOSE, n packets
        x, y, z, n, gap = int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8]), float(sys.argv[9])
        for i in range(n):
            peer.door("open" if i % 2 == 0 else "close", x, y, z)
            time.sleep(gap)
        print("sent", n, "door packets", flush=True)
        time.sleep(1)
        return
    if cmd == "door":
        peer.door(sys.argv[5], int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8]))
        print("sent door", sys.argv[5:9], flush=True)
        time.sleep(2)
        return
    if cmd == "enemy-near":
        # enemy-near <dx> <dy> <dz> <hold_s>: ask for the enemies of the room, take the first ENEMY_SPAWN the relay replays, and announce a SECOND enemy
        # of the same class, named ZNear_1, at the first one's place + (dx,dy,dz). Stays in the room for hold_s so the clients keep its puppet.
        dx, dy, dz, hold = float(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8])
        peer.send(5, 0x0A)                                  # WORLD_REQUEST_ENEMIES (empty payload)
        t0 = time.time()
        while not peer.spawns and time.time() - t0 < 15:
            time.sleep(0.2)
        if not peer.spawns:
            sys.exit("no ENEMY_SPAWN replayed by the relay")
        body = peer.spawns[0][6:]
        n = body[0]
        rest = body[1 + n:]
        cl = rest[0]
        cls, (x, y, z), tail = rest[:1 + cl], struct.unpack("<fff", rest[1 + cl:13 + cl]), rest[13 + cl:]
        newname = b"ZNear_1"
        peer.send(3, 1, bytes([len(newname)]) + newname + cls + struct.pack("<fff", x + dx, y + dy, z + dz) + tail)
        print(f"announced ZNear_1 ({cls[1:].decode('ascii', 'replace')}) at {(round(x + dx), round(y + dy), round(z + dz))}, the original is at {(round(x), round(y), round(z))}", flush=True)
        time.sleep(hold)
        return
    if cmd == "sweep":
        prefix, a, b, delay, clog = sys.argv[5], int(sys.argv[6]), int(sys.argv[7]), float(sys.argv[8]), sys.argv[9]
        sent = []
        for n in range(a, b + 1):
            path = f"{prefix}.TheWorld:PersistentLevel.Main_Sequence.SeqEvent_Touch_{n}"
            sent.append((time.time(), n))
            peer.trigger(path)
            print(f"{time.strftime('%H:%M:%S')} sent Touch_{n}", flush=True)
            time.sleep(delay)
        time.sleep(5)  # the client flushes its log late
        lines = log_lines_wall(clog)
        for i, (t, n) in enumerate(sent):
            t_end = sent[i + 1][0] if i + 1 < len(sent) else t + delay + 5
            hits = [l for (w, l) in lines if t - 1 <= w < t_end - 1]
            print(f"Touch_{n}: " + ("no effect in log" if not hits else ""))
            for l in hits:
                print("    " + l[:160])
    peer.alive = False


if __name__ == "__main__":
    main()
