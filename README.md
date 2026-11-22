# STABILOCK 4015 memory card tools

Read, check, keep and restore the SRAM memory cards of the Schlumberger / Wavetek
STABILOCK 4015 radio test set: the option programs (TRACKING, POCSAG, EAMPS, EDACS,
TRUNKING, …) and the user cards with set-ups and Autorun programs.

The cards are 30 to 40 years old and run on a lithium cell. When the cell dies, the
program is gone. This project describes the cards completely and gives you what you
need to save them.

## Contents

| Path | What |
|---|---|
| `docs/memory_card_1.2.PDF` | the full description: card, slot, adapter, format, program files, how the instrument uses a card, known cards |
| `hardware/4015_SRAM_Card_adapter_1.1.PDF` | build sheet for the adapter from the 34-contact card to a 32-pin DIP plug for a device programmer |
| `tools/cardcheck.py` | checks a card image read with **any** programmer on **any** operating system |
| `tools/cardprog.py` | reads and writes cards of 32 to 256 KB with an XGecu TL866 / T48 through `minipro` (Linux), with checks and a backup before every write |
| `tools/mkcard.py` | lists, extracts and builds card images |
| `tools/known_cards.csv` | the known cards with their SHA-256 sums |

## Quick start

1. Build the adapter from the build sheet.
2. Read the card in your programmer's software: as **DS1245Y** (128 KB) with jumper J1 open,
   or as **DS1230Y** (32 KB) with J1 on Vcc. Read twice and compare the files.
3. Check the file:

   ```
   python3 tools/cardcheck.py MYCARD.BIN --out MYCARD_CLEAN.BIN
   ```

   It cuts the read to the card's size, tests the address lines, checks every program
   record against its sum and tells you whether the card is a known one.

With a TL866 under Linux: `python3 tools/cardprog.py read MYCARD.BIN --large`.

## Card images

The images themselves are original Wavetek software and are not part of this repository.
They are offered for download, with the same SHA-256 sums, at
[dc3ax.de › Instruments › STABILOCK 4015 › Memory cards](https://dc3ax.de/en/instruments/stabilock-4015/memory-cards/).
Cards not in `known_cards.csv` are wanted: please get in touch via [dc3ax.de](https://dc3ax.de).

## Support

If these tools saved one of your cards, you can support the work via [Ko-fi](https://ko-fi.com/dc3ax).

## Licence

Software: GNU General Public License, version 3 or later (GPL-3.0-or-later, `LICENSE`): use, change and pass it on freely; changed versions you pass on stay under the GPL, with their source code. Up to 2026-11-22 the tools were released under MIT; copies obtained then keep that licence. Documentation and hardware: CC BY 4.0 (`LICENSE-docs.md`).
STABILOCK is a registered trademark of its owner. This project is not a product of the
instrument's maker and comes without any warranty.

© 2026 Ulrich Prinz, OE3UPR / DC3AX / AG1U – [dc3ax.de](https://dc3ax.de)
