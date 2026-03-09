#!/usr/bin/env python3
"""
Convert agentic-patterns.md to agentic-patterns.docx.

All 7 code blocks contain ASCII-art diagrams (box-drawing characters + arrows).
Strategy:
  1. For each such block, render to a PNG image using Pillow + Courier New.
  2. Replace the fenced block in markdown with an image reference.
  3. Run pandoc to produce the final DOCX.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC_MD = Path(__file__).parent / "agentic-patterns.md"
OUT_DOCX = Path(__file__).parent / "agentic-patterns.docx"
PANDOC = shutil.which("pandoc") or "/opt/homebrew/bin/pandoc"

FONT_PATH = "/System/Library/Fonts/Supplemental/Courier New.ttf"
FONT_SIZE = 18
PADDING = 24
BG_COLOR = (248, 248, 250)   # very light grey background
TEXT_COLOR = (30, 30, 30)
BORDER_COLOR = (200, 200, 210)
SCALE = 2   # 2× for crisp rendering then downscale


def render_ascii_diagram(text: str, out_path: Path) -> None:
    """Render a block of ASCII/Unicode art to a PNG image."""
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE * SCALE)
    except OSError:
        font = ImageFont.load_default()

    lines = text.splitlines()
    # measure character cell
    dummy = Image.new("RGB", (1, 1))
    dd = ImageDraw.Draw(dummy)
    bbox = dd.textbbox((0, 0), "M", font=font)
    char_w = bbox[2] - bbox[0]
    char_h = (bbox[3] - bbox[1]) + int(FONT_SIZE * SCALE * 0.35)

    max_chars = max((len(l) for l in lines), default=1)
    img_w = max_chars * char_w + PADDING * SCALE * 2
    img_h = len(lines) * char_h + PADDING * SCALE * 2

    img = Image.new("RGB", (img_w, img_h), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # light border
    draw.rectangle([0, 0, img_w - 1, img_h - 1], outline=BORDER_COLOR, width=2 * SCALE)

    for i, line in enumerate(lines):
        y = PADDING * SCALE + i * char_h
        draw.text((PADDING * SCALE, y), line, font=font, fill=TEXT_COLOR)

    # downscale for nicer anti-aliasing
    final_w = img_w // SCALE
    final_h = img_h // SCALE
    img = img.resize((final_w, final_h), Image.LANCZOS)
    img.save(out_path, "PNG", optimize=True)


# Match plain (no language tag) fenced code blocks only
FENCE_RE = re.compile(r"```\n(.*?)```", re.DOTALL)
BOX_CHARS = set("┌┐└┘├┤─│╔╗╚╝→←↑↓↔──")


def is_diagram(content: str) -> bool:
    return any(c in content for c in BOX_CHARS)


def patch_markdown(src_text: str, img_dir: Path) -> str:
    img_dir.mkdir(parents=True, exist_ok=True)
    counter = [0]

    def replace(m: re.Match) -> str:
        content = m.group(1)
        if not is_diagram(content):
            return m.group(0)   # leave non-diagram code blocks alone

        counter[0] += 1
        idx = counter[0]
        png_path = img_dir / f"diagram_{idx:02d}.png"
        print(f"  Rendering diagram {idx} ({len(content.splitlines())} lines) → {png_path.name}")
        render_ascii_diagram(content.rstrip("\n"), png_path)
        return f"![Diagram {idx}]({png_path})\n"

    return FENCE_RE.sub(replace, src_text)


def main() -> None:
    if not Path(PANDOC).exists():
        sys.exit(f"pandoc not found. Run: brew install pandoc")

    print("Reading source markdown…")
    src_text = SRC_MD.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="cortex_docx_") as tmp:
        img_dir = Path(tmp) / "diagrams"
        print("Rendering ASCII-art diagrams…")
        patched = patch_markdown(src_text, img_dir)

        patched_md = Path(tmp) / "agentic-patterns-patched.md"
        patched_md.write_text(patched, encoding="utf-8")

        print("Running pandoc…")
        result = subprocess.run(
            [
                PANDOC,
                str(patched_md),
                "-o", str(OUT_DOCX),
                "--from", "markdown",
                "--to", "docx",
                "--highlight-style", "tango",
                "--wrap", "none",
            ],
            capture_output=True,
            text=True,
            cwd=tmp,
        )
        if result.returncode != 0:
            sys.exit(f"pandoc failed:\n{result.stderr}")

    print(f"\nDone. Output: {OUT_DOCX}")


if __name__ == "__main__":
    main()
