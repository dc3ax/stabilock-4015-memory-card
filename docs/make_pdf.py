#!/usr/bin/env python3
# Copyright (c) 11.2026 Ulrich Prinz, OE3UPR / DC3AX / AG1U
# SPDX-License-Identifier: MIT
"""Build docs/memory_card.pdf from docs/memory_card.md.

    python3 make_pdf.py

Needs pandoc and WeasyPrint. The table of contents is generated from the chapter (#)
and section (##) headings and put where the marker <!-- TOC --> stands; the page numbers
come from the print style (manual.css).
"""
import os, re, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "memory_card.md")
PDF = os.path.join(HERE, "memory_card.pdf")


def slug(text):
    """The identifier pandoc gives a heading (gfm auto identifiers)."""
    s = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return re.sub(r"\s", "-", s)


def toc(md):
    items, chapter, in_code = [], 0, False
    for line in md.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        m = re.match(r"^(#{1,2}) (.+)$", line)
        if not m:
            continue
        text = m.group(2).strip()
        if m.group(1) == "#":
            numbered = text != "Revisions"
            chapter += numbered
            label = ("%d %s" % (chapter, text)) if numbered else text
            items.append('<li class="chapter"><a href="#%s">%s</a></li>' % (slug(text), label))
        else:
            items.append('<li class="section"><a href="#%s">%s</a></li>' % (slug(text), text))
    return '<nav class="toc">\n<ul>\n%s\n</ul>\n</nav>' % "\n".join(items)


def main():
    md = open(SRC).read()
    md = md.replace("<!-- TOC -->", toc(md))
    with tempfile.NamedTemporaryFile("w", suffix=".md", dir=HERE, delete=False) as f:
        f.write(md)
        tmp = f.name
    try:
        subprocess.run(["pandoc", tmp, "-f", "gfm", "-t", "html5", "-s", "--section-divs",
                        "--metadata", "title=4015 Memory Card", "-c", "manual.css",
                        "--pdf-engine=weasyprint", "-o", PDF], check=True, cwd=HERE)
    finally:
        os.unlink(tmp)
    print("written:", PDF)


if __name__ == "__main__":
    main()
