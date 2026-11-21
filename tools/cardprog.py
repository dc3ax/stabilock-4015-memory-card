#!/usr/bin/env python3
# Copyright (c) 10.2026 Ulrich Prinz, OE3UPR / DC3AX / AG1U
# SPDX-License-Identifier: MIT
"""Read or write a 4015 memory card in the device programmer, with checks.

Read:   cardprog.py read  OUT.BIN [--large]
Write:  cardprog.py write IMAGE.BIN [--yes]
Check:  cardprog.py check FILE.BIN

Uses `minipro` (TL866 / T48 programmers) with the device type DS1230Y(RW) and the adapter
of docs/memory_card_*.PDF. With another programmer, read the card with its own software and
check the file with cardcheck.py.

read   reads the card twice, compares the two reads, tests the address lines and
       lists the directory.
       --large reads with DS1245Y(RW) (128 KB) on a 32-pin adapter that also wires A15 and
       A16 (docs/memory_card_*.PDF, "Reading and Writing a Card"). The card size is taken from the
       size code in directory sector 2; the 128 KB read must repeat the card content
       (a 64 KB card ignores A16), and only the card's own size is saved.
write  first reads the card that is in the adapter. If its content is not one of the
       images already kept in this folder, it is saved to backups/ before anything is
       written. Then the image is written and the card is read back and compared.
check  runs the same tests on a file.
"""
import argparse, datetime, hashlib, os, subprocess, sys, tempfile

import mkcard

DEVICE = "DS1230Y(RW)"
SIZE = 32768
LARGE_DEVICE = "DS1245Y(RW)"
LARGE_SIZE = 131072
HERE = os.path.dirname(os.path.abspath(__file__))
BACKUPS = os.path.join(os.getcwd(), "backups")           # unknown card content is saved here before a write
KNOWN = os.path.join(HERE, "known_cards.csv")

def minipro(*args, device=DEVICE):
    r = subprocess.run(["minipro", "-p", device, *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("minipro failed (programmer on a USB 2 hub? adapter seated?)")
    return r.stdout + r.stderr

def read_once(device=DEVICE):
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "card.bin")
        minipro("-r", f, device=device)
        return open(f, "rb").read()

def read_card(device=DEVICE):
    a, b = read_once(device), read_once(device)
    if a != b:
        n = sum(x != y for x, y in zip(a, b))
        raise SystemExit("two reads differ in %d bytes: loose or too long wires" % n)
    return a

def dead_address_lines(img):
    """Address bits that make no difference anywhere: that line does not reach the card."""
    dead = []
    for bit in range(len(img).bit_length() - 1):
        m = 1 << bit
        if all(img[a] == img[a | m] for a in range(len(img)) if not a & m):
            dead.append(bit)
    return dead

def problems(img, size=SIZE):
    p = []
    if len(img) != size:
        p.append("length is %d bytes, not %d: wrong device type" % (len(img), size))
    elif len(set(img)) == 1:
        p.append("all bytes are %02X: no contact or no chip select" % img[0])
    else:
        dead = dead_address_lines(img)
        if dead:
            p.append("address line(s) %s have no effect" % ", ".join("A%d" % b for b in dead))
    return p

def known_images():
    """SHA-1 of every known image: the published list (by SHA-256, compared separately)
    and the .BIN files in the current folder. Used to decide whether a card's content
    must be saved before it is overwritten."""
    known = {}
    for root, _, files in os.walk(os.getcwd()):
        for f in sorted(files):
            path = os.path.join(root, f)
            if f.upper().endswith(".BIN") and os.path.getsize(path) in (32768, 65536, 131072):
                known.setdefault(hashlib.sha1(open(path, "rb").read()).digest(), os.path.relpath(path))
    return known

def known_sha256():
    import csv
    try:
        return {r["image_sha256"]: "%s %s" % (r["program"], r["version"]) for r in csv.DictReader(open(KNOWN))}
    except OSError:
        return {}

def describe(img):
    if img[4:12] != b"<4015.A>":
        print("  no 4015 signature")
        return
    info = mkcard.parse(img)
    print("  card kind %r" % info["kind"])
    size = mkcard.card_size(img)
    if size and size > len(img):
        print("  WARNING: this is a %d KB card; only the lower %d KB were read, because the 28-pin\n"
              "  adapter leaves card contact 22 (A15) and up open. See docs/memory_card_*.PDF."
              % (size // 1024, len(img) // 1024))
    for k, n, f, c in info["files"]:
        print("  %s %-10s first sector %3d  count %3d" % (k, n, f, c))
        if k == "P":
            for line in mkcard.describe_records(img, f):
                print("      " + line)

def report(img, size=SIZE):
    p = problems(img, size)
    for line in p:
        print("  FAULT: " + line)
    if not p:
        describe(img)
    return not p

def cmd_check(a):
    img = open(a.file, "rb").read()
    print("%s: %d bytes" % (a.file, len(img)))
    if not report(img, len(img) if len(img) in (32768, 65536, 131072, 262144) else SIZE):
        raise SystemExit(1)

def large_read():
    """Read with the 128 KB device type and cut the image to the card's own size."""
    raw = read_card(LARGE_DEVICE)
    print("card read twice with %s, both reads identical" % LARGE_DEVICE)
    if len(raw) != LARGE_SIZE:
        raise SystemExit("read gave %d bytes, not %d" % (len(raw), LARGE_SIZE))
    size = mkcard.card_size(raw)
    if raw[4:12] != b"<4015.A>" or not size:
        raise SystemExit("no 4015 signature or no valid size code; raw read kept nowhere, check the wiring")
    size = min(size, LARGE_SIZE)
    copies = [raw[i:i + size] for i in range(0, LARGE_SIZE, size)]
    if any(c != copies[0] for c in copies):
        raise SystemExit("size code says %d KB, but the 128 KB read does not repeat every %d KB:\n"
                         "A15/A16 not wired as described, or the size code is wrong" % (size // 1024, size // 1024))
    print("size code: %d KB card; the 128 KB read repeats it %d times, as it must" % (size // 1024, len(copies)))
    return copies[0]

def cmd_read(a):
    if a.large:
        img = large_read()
        ok = report(img, len(img))
    else:
        img = read_card()
        print("card read twice, both reads identical")
        ok = report(img)
    open(a.out, "wb").write(img)
    name = known_images().get(hashlib.sha1(img).digest()) or known_sha256().get(hashlib.sha256(img).hexdigest())
    print("saved as %s%s" % (a.out, " (same content as %s)" % name if name else ""))
    if not ok:
        raise SystemExit(1)

def cmd_write(a):
    new = open(a.image, "rb").read()
    if len(new) != SIZE:
        raise SystemExit("%s is %d bytes; a 32 KB card needs %d" % (a.image, len(new), SIZE))
    print("image %s:" % a.image)
    describe(new)

    print("card in the adapter:")
    old = read_card()
    if not report(old):
        raise SystemExit("card does not read properly; nothing written")
    if old == new:
        print("the card already holds this image; nothing to do")
        return
    name = known_images().get(hashlib.sha1(old).digest()) or known_sha256().get(hashlib.sha256(old).hexdigest())
    if name:
        print("  content is the same as %s, so nothing is lost" % name)
    else:
        os.makedirs(BACKUPS, exist_ok=True)
        bak = os.path.join(BACKUPS, datetime.datetime.now().strftime("card_%Y%m%d_%H%M%S.BIN"))
        open(bak, "wb").write(old)
        print("  content is not among the kept images; saved as %s" % os.path.relpath(bak))
    if not a.yes and input("overwrite this card? (yes/no) ").strip().lower() != "yes":
        raise SystemExit("nothing written")

    minipro("-w", a.image)
    back = read_card()
    if back != new:
        diff = [i for i in range(SIZE) if back[i] != new[i]]
        print("FAULT: %d bytes differ after writing, first at 0x%04X (wrote %02X, reads %02X)"
              % (len(diff), diff[0], new[diff[0]], back[diff[0]]))
        if back == old:
            print("the card is unchanged: write-protect switch on?")
        raise SystemExit(1)
    print("written and read back: identical in all %d bytes" % SIZE)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read"); r.add_argument("out"); r.set_defaults(func=cmd_read)
    r.add_argument("--large", action="store_true", help="32-pin adapter, device DS1245Y(RW), cards up to 128 KB")
    w = sub.add_parser("write"); w.add_argument("image"); w.set_defaults(func=cmd_write)
    w.add_argument("--yes", action="store_true", help="do not ask before overwriting")
    c = sub.add_parser("check"); c.add_argument("file"); c.set_defaults(func=cmd_check)
    a = ap.parse_args()
    a.func(a)

if __name__ == "__main__":
    main()
