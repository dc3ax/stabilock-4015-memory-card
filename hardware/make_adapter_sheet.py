#!/usr/bin/env python3
# Copyright (c) 10.2026 Ulrich Prinz, OE3UPR / DC3AX / AG1U
# SPDX-License-Identifier: CC-BY-4.0 (the sheet), MIT (this script)
"""Make the build sheet for the memory card adapter.

    python3 make_adapter_sheet.py

Writes hardware/4015_SRAM_Card_adapter.pdf with WeasyPrint. The wiring is defined once,
below; the description is in docs/memory_card.pdf.
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

# DS1245 / DS1250 DIP-32 pin -> (signal, card contact). A 28-pin part (62256, DS1230, 28C256)
# sits in pins 3-30. Pin 30 goes through jumper J1 (Vcc for DS1230, open for DS1245, A17 for DS1250).
DIP = {1: ("(A18) open", "&ndash;"), 2: ("A16", "23"), 3: ("A14", "2"), 4: ("A12", "3"), 5: ("A7", "5"),
       6: ("A6", "9"), 7: ("A5", "11"), 8: ("A4", "13"), 9: ("A3", "15"), 10: ("A2", "17"),
       11: ("A1", "19"), 12: ("A0", "24"), 13: ("D0", "26"), 14: ("D1", "28"), 15: ("D2", "30"),
       16: ("GND", "33 + 34"), 17: ("D3", "32"), 18: ("D4", "31"), 19: ("D5", "29"), 20: ("D6", "27"),
       21: ("D7", "25"), 22: ("/CS", "20"), 23: ("A10", "18"), 24: ("/OE", "16"), 25: ("A11", "14"),
       26: ("A9", "12"), 27: ("A8", "10"), 28: ("A13", "6"), 29: ("/WE", "4"), 30: ("J1", "1 / 21"),
       31: ("A15", "22"), 32: ("Vcc +5 V", "1")}
OPEN = {7: "not connected", 8: "not connected"}

card = {}
for pin, (sig, contacts) in DIP.items():
    if pin in (1, 30):
        continue
    for c in contacts.split("+"):
        card[int(c)] = (sig, str(pin))
card[1] = ("Vcc +5 V", "32, J1&rarr;30")
card[21] = ("A17", "J1&rarr;30")

rows_card = ""
for a, b in zip(range(1, 18), range(18, 35)):
    def cell(n):
        if n in card:
            return "<td class=n>%d</td><td nowrap>%s</td><td class=n>%s</td>" % (n, card[n][0], card[n][1])
        return "<td class=n>%d</td><td class=o nowrap>%s</td><td class=n>&ndash;</td>" % (n, OPEN[n])
    rows_card += "<tr>%s<td class=gap></td>%s</tr>\n" % (cell(a), cell(b))

rows_dip = ""
for left in range(1, 17):
    right = 33 - left
    rows_dip += ("<tr><td class=n nowrap>%s</td><td class=r nowrap>%s</td><td class=pl>%d</td><td class=chip></td>"
                 "<td class=pr>%d</td><td nowrap>%s</td><td class=n>%s</td></tr>\n"
                 % (DIP[left][1], DIP[left][0], left, right, DIP[right][0], DIP[right][1]))

html = """<!doctype html><html><head><meta charset="utf-8"><title>4015 memory card adapter</title>
<style>
@page { size: A4; margin: 14mm; }
body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 9.5pt; }
h1 { font-size: 15pt; margin: 0 0 2pt 0; }
h2 { font-size: 11.5pt; margin: 9pt 0 3pt 0; page-break-after: avoid; }
table { page-break-inside: avoid; }
p, li { margin: 2pt 0; }
table { border-collapse: collapse; }
th, td { border: 0.6pt solid #000; padding: 2pt 7pt; }
th { background: #ddd; }
td.n { text-align: center; font-weight: bold; }
td.r { text-align: right; }
td.o { color: #555; font-style: italic; }
td.gap, td.chip { border: none; }
td.gap { width: 10pt; }
td.chip { width: 70pt; background: #eee; border-left: 0.6pt solid #000; border-right: 0.6pt solid #000; }
td.pl { text-align: right; font-weight: bold; }
td.pr { text-align: left; font-weight: bold; }
.small { font-size: 8pt; color: #333; }
</style></head><body>
<h1>Schlumberger / Wavetek 4015 &ndash; memory card adapter for a device programmer</h1>
<p>Connects a Panasonic 34-contact SRAM card (32 KB to 256 KB) to a 32-pin DIP plug in the pin order of the
32-pin battery-backed RAMs DS1245 (128 KB) and DS1250 (512 KB). A 28-pin part (62256, DS1230, 28C256) sits in
pins 3&ndash;30 of that outline, so 32 KB cards are handled as a DS1230Y and larger cards as a DS1245Y.
Pin numbers of the card socket are those of connector ST80 in the instrument (pin 1 = supply, pin 34 = ground).</p>
<table style="margin-top:4pt">
<tr><th>Jumper J1 (DIP pin 30)</th><th>Device type</th><th>Cards</th></tr>
<tr><td>to card contact 1 (Vcc)</td><td>DS1230Y(RW)</td><td>32 KB, read and write</td></tr>
<tr><td>open</td><td>DS1245Y(RW)</td><td>64 and 128 KB (a 32 KB card reads four times over)</td></tr>
<tr><td>to card contact 21 (A17)</td><td>DS1250Y(RW)</td><td>256 KB, not tried yet</td></tr>
</table>
<p class=small>Never leave J1 on Vcc with DS1245Y or DS1250Y selected.</p>

<h2>1. Wiring, sorted by card socket contact</h2>
<table>
<tr><th width=55 nowrap>Card</th><th width=140 nowrap>Signal</th><th width=65 nowrap>DIP-32</th><td class=gap width=14></td><th width=55 nowrap>Card</th><th width=140 nowrap>Signal</th><th width=65 nowrap>DIP-32</th></tr>
""" + rows_card + """</table>
<p class=small>31 wires and jumper J1. Card contacts 33 and 34 both go to DIP pin 16. Contacts 7 and 8 stay open
(their use on cards above 256 KB is not known). DIP pin 1 stays open.</p>

<h2>2. The same wiring seen from the DIP plug (top view, notch at the top)</h2>
<table>
<tr><th width=70 nowrap>Card</th><th width=85 nowrap>Signal</th><th width=45 nowrap>Pin</th><td class=chip width=90 nowrap style="text-align:center">DIP-32</td><th width=45 nowrap>Pin</th><th width=85 nowrap>Signal</th><th width=70 nowrap>Card</th></tr>
""" + rows_dip + """</table>

<h2 style="page-break-before: always">3. Before a card is connected</h2>
<ol>
<li>Find pin 1 of the socket by comparing with ST80 in the instrument. With a spare card inserted, contacts 33 and
34 must show continuity to each other; contact 1 must not be joined to them.</li>
<li>Check every wire of the finished adapter for continuity and for shorts to its neighbours.</li>
<li>Keep the wires to a few centimetres.</li>
<li>Never plug the adapter into the programmer turned round: that puts 5 V on the ground side of a card with a battery.</li>
</ol>

<h2>4. Programmer settings and first use</h2>
<ul>
<li>Device: DS1230Y or DS1230AB (32 KB battery-backed RAM) with J1 on Vcc; DS1245Y with J1 open for larger cards.
If DS1230 is not available: 28C256 / AT28C256 with software data protection switched <b>off</b>. Not 27C256.</li>
<li>First action is a <b>read</b>: read a card and check the file with <i>tools/cardcheck.py</i>. A card listed in
<i>known_cards.csv</i> proves adapter and settings in one step.</li>
<li>Write to a spare card first, read it back, then try it in the instrument.</li>
</ul>
<p class=small>Signals marked / are active low. Source and background: docs/memory_card.pdf.
Pin assignment from the instrument's schematic (connector ST80), in agreement with an independent pin table for the
BN-032MC and with the firmware's card access routines. The 28-pin form of this adapter (pins 3&ndash;30) has been
in use since 2026-10-13; the 32-pin form with J1 read its first 64 KB card on 2026-11-21.</p>
</body></html>
"""
pdf = os.path.join(HERE, "4015_SRAM_Card_adapter.pdf")
subprocess.run(["weasyprint", "-", pdf], input=html.encode("utf-8"), check=True,
               stderr=subprocess.DEVNULL)
print("written:", pdf)
