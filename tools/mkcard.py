#!/usr/bin/env python3
# Copyright (c) 10.2026 Ulrich Prinz, OE3UPR / DC3AX / AG1U
# SPDX-License-Identifier: MIT
"""Build or inspect a Wavetek/Schlumberger 4015 memory card image (program card).

Build:    mkcard.py build  PROGRAM.bin  OUT.BIN  --name "MyProg" --version "0.01"
              [--load 0x208200] [--size 32768] [--data BLOCK.bin]
              [--file TYPE:NAME:SECTOR:PATH ...]
Inspect:  mkcard.py info   CARD.BIN
Extract:  mkcard.py extract CARD.BIN OUT_PROGRAM.bin
Get file: mkcard.py get    CARD.BIN NAME OUT_FILE

--file adds a further file: a directory entry of the given type (T = shown without a
name ending) and the content of PATH from the given sector on. `get` writes the
sectors of the directory entry called NAME to a file.

Card layout (see docs/memory_card_*.PDF): 512-byte sectors numbered from 1; sector 1 and 2 are
directory sectors with 16-byte entries; sectors 3-4 are a 1 KB data block; the program
file starts in sector 5 as an 'H' record followed by an 'F' record.
"""
import argparse, struct, sys

SECTOR = 512
RAM_BASE = 0x200000
PROGRAM_SECTOR = 5                      # 1-based; byte offset 0x800
PROGRAM_OFFSET = (PROGRAM_SECTOR - 1) * SECTOR
LABEL = ["**********", "*SI 4015 *", "* MEMORY *", "*  CARD  *", "**********",
         "*USE ONLY*", "*  IN    *", "*SI 4015 *", "**********", "          "]

def entry(kind, name, first=0, count=0):
    name = name.encode("latin1")[:10].ljust(10, b" ")
    return bytes([ord(kind), 0]) + name + struct.pack(">HH", first, count)

def dir_sector(header, entries):
    s = header + b"".join(entries)
    s += entry(" ", "") * ((SECTOR - len(s)) // 16)
    assert len(s) == SECTOR
    return s

def h_record(program, load):
    start = load - RAM_BASE
    end = start + len(program) - 1                      # inclusive
    if not (0 <= start and end <= 0xFFFFF):
        raise SystemExit("load range does not fit the 5-digit address fields")
    head = ("H%05X%05X%04X" % (start, end, sum(program) & 0xFFFF)).encode() + b"\x00"
    return head + program

def build(program, name, version, load=0x208200, size=32768, data_block=None, label=None, files=()):
    label = label or LABEL
    # sector 1: signature, link to sector 2, label in the free slots (pre-allocated in pairs)
    hdr1 = bytes([0x00, 0x04, 0x02, ord("P")]) + b"<4015.A>" + struct.pack(">HH", 2, 0)
    # ten slots, pre-allocated as two sectors each: first sectors 3, 5, ... 21
    e1 = [entry(" ", text, 3 + 2 * i, 2) for i, text in enumerate(label[:10])]
    img = dir_sector(hdr1, e1)
    # sector 2: file directory
    hdr2 = bytes([0x00, 0x04, 0x02, ord("P")]) + b"SerienNr" + struct.pack(">HH", 0, 0)
    extra = [(k, n, int(sec), open(path, "rb").read()) for k, n, sec, path in files]
    img += dir_sector(hdr2, [entry("P", name, PROGRAM_SECTOR, 0x19), entry("V", version)]
                      + [entry(k, n, sec, -(-len(d) // SECTOR)) for k, n, sec, d in extra])
    # sectors 3-4: data block
    blk = (data_block or b"")[:2 * SECTOR].ljust(2 * SECTOR, b"\x00")
    img += blk
    # program file
    rec = h_record(program, load)
    rec += b"\xFF" * (-len(rec) % SECTOR)
    img += rec + b"F0000000000crcs\x00"
    if len(img) > size:
        raise SystemExit("program does not fit: image needs %d bytes, card has %d" % (len(img), size))
    img = bytearray(img + b"\xFF" * (size - len(img)))
    for k, n, sec, d in extra:
        off = (sec - 1) * SECTOR
        if off < len(rec) + PROGRAM_OFFSET + 16 or off + len(d) > size:
            raise SystemExit("file %s at sector %d does not fit" % (n, sec))
        d += b"\x00" * (-len(d) % SECTOR)
        img[off:off + len(d)] = d
    return bytes(img)

def parse(img):
    info = {"kind": chr(img[3]), "signature": img[4:12].decode("latin1"), "files": []}
    for sec in (0, SECTOR):
        for i in range(1, 32):
            e = img[sec + 16 * i: sec + 16 * i + 16]
            if e[0] != 0x20:
                first, count = struct.unpack(">HH", e[12:16])
                info["files"].append((chr(e[0]), e[2:12].decode("latin1"), first, count))
    return info

def card_size(img):
    """Card size from the size code in directory sector 2 (number of 8 KB blocks), or None."""
    code = img[SECTOR + 1] if len(img) > SECTOR + 1 else 0
    return code * 8192 if code in (4, 8, 16, 32) else None

def records(img, first_sector, past_end=False):
    """Walk the record chain of a program file from its first sector.

    Yields (sector, type, start, end, stored_sum, data, complete, sum_ok). A record that runs past
    the end of img (a larger card read only in part) is yielded with complete=False. The chain ends
    at the first `F` record, as in the firmware's loader (card_load_program, loop end at 0x14FA2):
    records behind it are never loaded. With past_end=True the walk goes on behind an `F` as long
    as the next sector holds a record header, to show such leftovers.
    """
    sec = first_sector
    while (sec - 1) * SECTOR + 16 <= len(img):
        off = (sec - 1) * SECTOR
        h = img[off:off + 16]
        t = chr(h[0])
        if t == "F":
            yield sec, t, 0, 0, 0, b"", True, True
            if not past_end:
                return
            sec += 1
            continue
        if t not in "H@012345678":
            return
        try:
            start, end, ck = int(h[1:6], 16), int(h[6:11], 16), int(h[11:15], 16)
        except ValueError:
            return
        if end < start:
            return
        n = end - start + 1
        data = img[off + 16: off + 16 + n]
        complete = len(data) == n
        yield sec, t, start, end, ck, data, complete, complete and (sum(data) & 0xFFFF) == ck
        sec += (16 + n + SECTOR - 1) // SECTOR

def describe_records(img, first_sector):
    """One text line per record of a program file."""
    lines = []
    ended = False
    for sec, t, start, end, ck, data, complete, ok in records(img, first_sector, past_end=True):
        if t == "F":
            lines.append("sector %3d  F end marker%s" % (sec, "" if not ended else " (behind the end, not loaded)"))
            ended = True
            continue
        base = RAM_BASE if t in "H@" else 0
        state = ("checksum %04X ok" % ck if ok else
                 "checksum %04X MISMATCH" % ck if complete else
                 "INCOMPLETE: runs past the end of the image (%d of %d bytes)" % (len(data), end - start + 1))
        lines.append("sector %3d  %s record: load 0x%06X-0x%06X, %d bytes, %s%s"
                     % (sec, t, base + start, base + end, end - start + 1, state,
                        "  (behind the end marker: not loaded)" if ended else ""))
    return lines or ["no record at sector %d" % first_sector]

def read_program(img, first_sector):
    """The first H (or @) record of the program file: (load address, data, stored sum, sum ok)."""
    for sec, t, start, end, ck, data, complete, ok in records(img, first_sector):
        if t in "H@":
            return RAM_BASE + start, data, ck, ok
    raise SystemExit("no H record in the program file starting at sector %d" % first_sector)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("program"); b.add_argument("out")
    b.add_argument("--name", required=True); b.add_argument("--version", default="0.01")
    b.add_argument("--load", type=lambda x: int(x, 0), default=0x208200)
    b.add_argument("--size", type=lambda x: int(x, 0), default=32768)
    b.add_argument("--data", help="file with up to 1 KB for the data block in sectors 3-4")
    b.add_argument("--file", action="append", default=[], metavar="TYPE:NAME:SECTOR:PATH")
    i = sub.add_parser("info"); i.add_argument("card")
    x = sub.add_parser("extract"); x.add_argument("card"); x.add_argument("out")
    g = sub.add_parser("get"); g.add_argument("card"); g.add_argument("name"); g.add_argument("out")
    a = ap.parse_args()
    if a.cmd == "build":
        prog = open(a.program, "rb").read()
        data = open(a.data, "rb").read() if a.data else None
        img = build(prog, a.name, a.version, a.load, a.size, data, files=[f.split(":", 3) for f in a.file])
        open(a.out, "wb").write(img)
        print("wrote %s: %d bytes, program %d bytes at 0x%06X" % (a.out, len(img), len(prog), a.load))
    else:
        img = open(a.card, "rb").read()
        info = parse(img)
        if a.cmd == "info":
            print("card kind %r, signature %r, %d bytes" % (info["kind"], info["signature"], len(img)))
            size = card_size(img)
            if size and size > len(img):
                print("  WARNING: size code says %d KB, the file holds only %d KB" % (size // 1024, len(img) // 1024))
            for k, n, f, c in info["files"]:
                print("  %s %-10s first sector %3d  count %3d" % (k, n, f, c))
                if k == "P":
                    for line in describe_records(img, f):
                        print("    " + line)
        elif a.cmd == "get":
            hit = [f for f in info["files"] if f[1].strip() == a.name.strip()]
            if not hit: raise SystemExit("no file %r on this card" % a.name)
            k, n, first, count = hit[0]
            open(a.out, "wb").write(img[(first - 1) * SECTOR:(first - 1 + count) * SECTOR])
            print("wrote %s: %d bytes from sector %d (type %s)" % (a.out, count * SECTOR, first, k))
        else:
            prog = [f for f in info["files"] if f[0] == "P"]
            if not prog: raise SystemExit("no program file on this card")
            load, data, ck, ok = read_program(img, prog[0][2])
            open(a.out, "wb").write(data)
            print("extracted %d bytes, load address 0x%06X, checksum %s" % (len(data), load, "ok" if ok else "MISMATCH"))

if __name__ == "__main__":
    main()
