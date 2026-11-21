#!/usr/bin/env python3
# Copyright (c) 11.2026 Ulrich Prinz, OE3UPR / DC3AX / AG1U
# SPDX-License-Identifier: MIT
"""Check a STABILOCK 4015 memory card image, whatever programmer it was read with.

    cardcheck.py DUMP.BIN [--out CARD.BIN]

DUMP.BIN is the raw file from any device programmer and any operating system, read as a
32 KB part (62256, DS1230, 28C256 pin order) or as a larger 32-pin part (DS1245, DS1250).
The tool

  - finds the card format signature and the card size code,
  - cuts a read that is larger than the card down to the card's size, after checking
    that the read repeats the card exactly (a larger part sees the card several times),
  - tests the address lines (an address line that changes nothing points to a wire
    that does not reach the card),
  - lists the directory and checks every record of a program file against its sum,
  - compares the card with the list of known cards (known_cards.csv), as a whole and
    by its program records alone: a used card differs in its saved settings but still
    carries the same program.

--out writes the card image cut to its own size. Exit status 0 = card good, 1 = fault.
Needs only Python 3; mkcard.py and known_cards.csv must lie next to this file.
"""
import argparse, csv, hashlib, os, sys

import mkcard

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWN = os.path.join(HERE, "known_cards.csv")
SIGNATURE = b"<4015.A>"


def dead_address_lines(img):
    """Address bits that make no difference anywhere: that line does not reach the card."""
    dead = []
    for bit in range(len(img).bit_length() - 1):
        m = 1 << bit
        if all(img[a] == img[a | m] for a in range(len(img)) if not a & m):
            dead.append(bit)
    return dead


def program_sha256(img):
    """SHA-256 over the records of the program file (type, load address, data), or ''."""
    info = mkcard.parse(img)
    progs = [f for f in info["files"] if f[0] == "P"]
    if not progs:
        return ""
    h = hashlib.sha256()
    for _sec, t, start, _end, _ck, data, _complete, _ok in mkcard.records(img, progs[0][2]):
        if t != "F":
            h.update(t.encode() + start.to_bytes(4, "big") + data)
    return h.hexdigest()


def load_known():
    try:
        return list(csv.DictReader(open(KNOWN)))
    except OSError:
        return []


def normalise(raw):
    """Return (card image, list of notes, list of faults)."""
    notes, faults = [], []
    if len(raw) < 1024 or raw[4:12] != SIGNATURE:
        if len(set(raw)) == 1:
            faults.append("all bytes are %02X: no contact, no chip select, or no supply to the card" % raw[0])
        elif len(raw) >= 24 and raw[4:12:2] == SIGNATURE[1::2] and raw[4:12:2] == raw[5:13:2]:
            faults.append("every byte appears twice: address line A0 does not reach the card")
        else:
            faults.append("no 4015 card signature at offset 4: not a 4015 card, or a wiring fault")
        return raw, notes, faults
    size = mkcard.card_size(raw)
    if not size:
        faults.append("no valid card size code in directory sector 2 (byte 1 = %02X)" % raw[513])
        return raw, notes, faults
    if len(raw) > size:
        copies = [raw[i:i + size] for i in range(0, len(raw) - len(raw) % size, size)]
        if any(c != copies[0] for c in copies):
            faults.append("the size code says %d KB, but the %d KB read does not repeat every %d KB: "
                          "an upper address line (A15, A16 ...) is not wired, or floats"
                          % (size // 1024, len(raw) // 1024, size // 1024))
            return raw, notes, faults
        notes.append("%d KB read of a %d KB card; it repeats the card %d times, as it must"
                     % (len(raw) // 1024, size // 1024, len(copies)))
        return copies[0], notes, faults
    if len(raw) < size:
        faults.append("this is a %d KB card, but only %d KB were read: the upper address lines are not "
                      "wired (a 28-pin adapter reads only 32 KB)" % (size // 1024, len(raw) // 1024))
    return raw, notes, faults


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump")
    ap.add_argument("--out", help="write the card image cut to its own size")
    a = ap.parse_args()
    raw = open(a.dump, "rb").read()
    print("%s: %d bytes" % (a.dump, len(raw)))
    img, notes, faults = normalise(raw)
    for n in notes:
        print("  " + n)
    if img[4:12] == SIGNATURE:
        dead = dead_address_lines(img)
        if dead:
            faults.append("address line(s) %s change nothing: wire not reaching the card"
                          % ", ".join("A%d" % b for b in dead))
        info = mkcard.parse(img)
        print("  card kind %r, %d KB" % (info["kind"], len(img) // 1024))
        for k, name, first, count in info["files"]:
            print("  %s %-10s first sector %3d  count %3d" % (k, name, first, count))
            if k == "P":
                for line in mkcard.describe_records(img, first):
                    print("      " + line)
                    if "MISMATCH" in line or "INCOMPLETE" in line:
                        if "not loaded" not in line:
                            faults.append("program record wrong: " + line.strip())
        whole = hashlib.sha256(img).hexdigest()
        prog = program_sha256(img)
        known = load_known()
        hit = [r for r in known if r["image_sha256"] == whole]
        same_prog = [r for r in known if prog and r["program_sha256"] == prog]
        print("  SHA-256 %s" % whole)
        if hit:
            r = hit[0]
            print("  KNOWN CARD: %s %s%s" % (r["program"], r["version"], ("  (" + r["note"] + ")") if r["note"] else ""))
        elif same_prog:
            r = same_prog[0]
            print("  KNOWN PROGRAM: %s %s; the card differs from the known images only outside the program "
                  "(saved settings or other files)" % (r["program"], r["version"]))
        elif prog and not any("INCOMPLETE" in f for f in faults):
            print("  program not in the list of known cards: please report it")
        for r in hit + same_prog:
            if r["note"].startswith("DAMAGED"):
                faults.append("this is the known DAMAGED image of %s %s" % (r["program"], r["version"]))
                break
    if a.out and img[4:12] == SIGNATURE:
        open(a.out, "wb").write(img)
        print("  card image written to %s (%d bytes)" % (a.out, len(img)))
    for f in faults:
        print("  FAULT: " + f)
    print("  result: %s" % ("GOOD" if not faults else "NOT GOOD"))
    sys.exit(1 if faults else 0)


if __name__ == "__main__":
    main()
