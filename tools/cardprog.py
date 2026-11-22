#!/usr/bin/env python3
# Copyright (c) 10.2026 Ulrich Prinz, OE3UPR / DC3AX / AG1U
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read or write a 4015 memory card of any size in the device programmer, with checks.

Read:   cardprog.py read  OUT.BIN  [--large | --a17]
Write:  cardprog.py write IMAGE.BIN [--large | --a17] [--yes]
Check:  cardprog.py check FILE.BIN

Uses `minipro` (TL866 / T48 programmers) and the adapter of docs/memory_card_*.PDF. With
another programmer, read the card with its own software and check the file with cardcheck.py.

Jumper J1 of the adapter and the option must agree:

  (none)    J1 on Vcc,  device DS1230Y(RW),  32 KB cards
  --large   J1 open,    device DS1245Y(RW),  64 and 128 KB cards (32 KB cards read as well)
  --a17     J1 on A17,  device DS1249Y(RW),  256 KB cards (not tried on a real card yet)

read   reads the card twice, compares the two reads, tests the address lines and lists the
       directory. A read larger than the card holds the card several times over; the card
       size is taken from the size code in directory sector 2, the read must repeat the card
       exactly, and only the card's own size is saved.
write  first reads the card that is in the adapter. If its content is not one of the images
       kept in the current folder or in known_cards.csv, it is saved to backups/ before
       anything is written. An image smaller than the device is written repeated, as the
       card sees it. Then the card is read back and compared.
check  runs the same tests on a file.
"""
import argparse, datetime, hashlib, os, subprocess, sys, tempfile

import mkcard

# option -> (minipro device, bytes per read, J1 setting, card sizes it serves)
MODES = {
    "small": ("DS1230Y(RW)", 32768, "on Vcc", (32768,)),
    "large": ("DS1245Y(RW)", 131072, "open", (32768, 65536, 131072)),
    "a17":   ("DS1249Y(RW)", 262144, "on A17", (32768, 65536, 131072, 262144)),
}
SIZES = (32768, 65536, 131072, 262144)
SIGNATURE = b"<4015.A>"
HERE = os.path.dirname(os.path.abspath(__file__))
BACKUPS = os.path.join(os.getcwd(), "backups")           # unknown card content is saved here before a write
KNOWN = os.path.join(HERE, "known_cards.csv")

def minipro(*args, device):
    r = subprocess.run(["minipro", "-p", device, *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("minipro failed (programmer on a USB 2 hub? adapter seated? J1 set?)")
    return r.stdout + r.stderr

def read_once(device):
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "card.bin")
        minipro("-r", f, device=device)
        return open(f, "rb").read()

def read_raw(mode):
    device, n, j1, _ = MODES[mode]
    a, b = read_once(device), read_once(device)
    if a != b:
        raise SystemExit("two reads differ in %d bytes: loose or too long wires"
                         % sum(x != y for x, y in zip(a, b)))
    if len(a) != n:
        raise SystemExit("%s read gave %d bytes, not %d" % (device, len(a), n))
    print("card read twice as %s (J1 %s), both reads identical" % (device, j1))
    return a

def period(raw):
    """Smallest card size whose copies make up the whole read (a card ignores the address
    lines above its own size), or the read's length."""
    for size in SIZES:
        if size < len(raw) and all(raw[i:i + size] == raw[:size] for i in range(size, len(raw), size)):
            return size
    return len(raw)

def card_from_raw(raw, strict):
    """Cut a read to the card's size. With a 4015 size code the read must repeat the card
    exactly (strict: else stop); without one the repetition alone gives the size."""
    size = mkcard.card_size(raw) if raw[4:12] == SIGNATURE else None
    if size is None or size >= len(raw):
        return raw[:min(size or len(raw), len(raw))] if size else raw[:period(raw)]
    copies = [raw[i:i + size] for i in range(0, len(raw), size)]
    if any(c != copies[0] for c in copies):
        msg = ("size code says %d KB, but the %d KB read does not repeat every %d KB:\n"
               "A15/A16/A17 not wired as described, J1 wrong, or the size code is wrong"
               % (size // 1024, len(raw) // 1024, size // 1024))
        if strict:
            raise SystemExit(msg)
        print("  WARNING: " + msg)
        return raw
    if len(copies) > 1:
        print("size code: %d KB card; the %d KB read repeats it %d times, as it must"
              % (size // 1024, len(raw) // 1024, len(copies)))
    return copies[0]

def dead_address_lines(img):
    """Address bits that make no difference anywhere: that line does not reach the card."""
    dead = []
    for bit in range(len(img).bit_length() - 1):
        m = 1 << bit
        if all(img[a] == img[a | m] for a in range(len(img)) if not a & m):
            dead.append(bit)
    return dead

def problems(img):
    p = []
    if len(img) not in SIZES:
        p.append("length is %d bytes, not a card size (32, 64, 128 or 256 KB)" % len(img))
    elif len(set(img)) == 1:
        p.append("all bytes are %02X: no contact, no chip select or no supply" % img[0])
    else:
        dead = dead_address_lines(img)
        if dead:
            p.append("address line(s) %s have no effect" % ", ".join("A%d" % b for b in dead))
    return p

def known_images():
    """SHA-1 of every .BIN image in the current folder and below. Used, with the published
    list, to decide whether a card's content must be saved before it is overwritten."""
    known = {}
    for root, _, files in os.walk(os.getcwd()):
        for f in sorted(files):
            path = os.path.join(root, f)
            if f.upper().endswith(".BIN") and os.path.getsize(path) in SIZES:
                known.setdefault(hashlib.sha1(open(path, "rb").read()).digest(), os.path.relpath(path))
    return known

def known_sha256():
    import csv
    try:
        return {r["image_sha256"]: "%s %s" % (r["program"], r["version"]) for r in csv.DictReader(open(KNOWN))}
    except OSError:
        return {}

def known_name(img):
    return known_images().get(hashlib.sha1(img).digest()) or known_sha256().get(hashlib.sha256(img).hexdigest())

def describe(img):
    if img[4:12] != SIGNATURE:
        print("  no 4015 signature")
        return
    info = mkcard.parse(img)
    print("  card kind %r" % info["kind"])
    size = mkcard.card_size(img)
    if size and size > len(img):
        print("  WARNING: this is a %d KB card; only the lower %d KB were read. Read it again with\n"
              "  %s (see the J1 table in docs/memory_card_*.PDF)."
              % (size // 1024, len(img) // 1024, "--a17" if size > 131072 else "--large"))
    for k, n, f, c in info["files"]:
        print("  %s %-10s first sector %3d  count %3d" % (k, n, f, c))
        if k == "P":
            for line in mkcard.describe_records(img, f):
                print("      " + line)

def report(img):
    p = problems(img)
    for line in p:
        print("  FAULT: " + line)
    if not p:
        describe(img)
    return not p

def cmd_check(a):
    img = open(a.file, "rb").read()
    print("%s: %d bytes" % (a.file, len(img)))
    if len(img) > 32768:
        img = card_from_raw(img, strict=False)
    if not report(img):
        raise SystemExit(1)

def cmd_read(a):
    img = card_from_raw(read_raw(a.mode), strict=True)
    ok = report(img)
    name = known_name(img)                   # before saving, or it finds its own file
    open(a.out, "wb").write(img)
    print("saved as %s%s" % (a.out, " (same content as %s)" % name if name else ""))
    if not ok:
        raise SystemExit(1)

def ask(question, a):
    if not a.yes and input(question + " (yes/no) ").strip().lower() != "yes":
        raise SystemExit("nothing written")

def cmd_write(a):
    device, n, j1, serves = MODES[a.mode]
    new = open(a.image, "rb").read()
    if len(new) not in SIZES:
        raise SystemExit("%s is %d bytes; a card image is 32, 64, 128 or 256 KB" % (a.image, len(new)))
    if len(new) not in serves:
        need = "--a17" if len(new) > 131072 else "--large"
        raise SystemExit("%s is a %d KB image: set J1 as described and use %s"
                         % (a.image, len(new) // 1024, need))
    code = mkcard.card_size(new) if new[4:12] == SIGNATURE else None
    if code and code != len(new):
        print("WARNING: the image's size code says %d KB, but the file is %d KB" % (code // 1024, len(new) // 1024))
    print("image %s (%d KB):" % (a.image, len(new) // 1024))
    describe(new)

    print("card in the adapter:")
    raw = read_raw(a.mode)
    old = card_from_raw(raw, strict=False)
    p = problems(old)
    if p:
        # Never write to a card that does not read properly. All FF in particular is a card
        # without supply from the programmer (J1 set for another device type, or no contact):
        # it then runs on its own cell, and the write pulses still reach it and spoil its
        # content (seen 2026-11-22 with J1 open and the 32 KB device type).
        for line in p:
            print("  FAULT: " + line)
        raise SystemExit("card does not read properly; nothing written. Check the card, the adapter\n"
                         "and that J1 and the option agree (none: J1 on Vcc; --large: J1 open)")
    describe(old)
    cap = mkcard.card_size(old) if old[4:12] == SIGNATURE else None
    if cap and cap < len(new):
        print("  WARNING: the card says it holds %d KB; the image needs %d KB" % (cap // 1024, len(new) // 1024))
    elif cap and cap > len(new):
        print("  NOTE: a %d KB card; the %d KB image fills it with copies, and its size code\n"
              "  makes the instrument treat the card as %d KB" % (cap // 1024, len(new) // 1024, len(new) // 1024))
    if old == new:
        print("the card already holds this image; nothing to do")
        return
    name = known_name(old)
    if name:
        print("  content is the same as %s, so nothing is lost" % name)
    else:
        os.makedirs(BACKUPS, exist_ok=True)
        bak = os.path.join(BACKUPS, datetime.datetime.now().strftime("card_%Y%m%d_%H%M%S.BIN"))
        open(bak, "wb").write(old)
        print("  content is not among the kept images; saved as %s" % os.path.relpath(bak))
    ask("overwrite this card?", a)

    image = new * (n // len(new))            # the card sees itself repeated in a larger device
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "write.bin")
        open(f, "wb").write(image)
        minipro("-w", f, device=device)
    back = read_raw(a.mode)
    if back != image:
        diff = [i for i in range(n) if back[i] != image[i]]
        print("FAULT: %d bytes differ after writing, first at 0x%05X (wrote %02X, reads %02X)"
              % (len(diff), diff[0], image[diff[0]], back[diff[0]]))
        if back == raw:
            print("the card is unchanged: write-protect switch on?")
        elif period(back) < len(new):
            print("the read-back repeats every %d KB: the card is smaller than the image"
                  % (period(back) // 1024))
        raise SystemExit(1)
    print("written and read back: identical in all %d bytes of the %d KB card"
          % (len(new), len(new) // 1024))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def mode_options(p):
        g = p.add_mutually_exclusive_group()
        g.add_argument("--large", dest="mode", action="store_const", const="large",
                       help="J1 open, device DS1245Y(RW): 64 and 128 KB cards")
        g.add_argument("--a17", dest="mode", action="store_const", const="a17",
                       help="J1 on A17, device DS1249Y(RW): 256 KB cards")
        p.set_defaults(mode="small")
    r = sub.add_parser("read"); r.add_argument("out"); r.set_defaults(func=cmd_read); mode_options(r)
    w = sub.add_parser("write"); w.add_argument("image"); w.set_defaults(func=cmd_write); mode_options(w)
    w.add_argument("--yes", action="store_true", help="do not ask before overwriting")
    c = sub.add_parser("check"); c.add_argument("file"); c.set_defaults(func=cmd_check)
    a = ap.parse_args()
    a.func(a)

if __name__ == "__main__":
    main()
