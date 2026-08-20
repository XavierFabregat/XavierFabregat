#!/usr/bin/env -S uv run --quiet --with pillow --with numpy python
"""Convert a photo into the ASCII portrait used by the profile README.

The photo itself is deliberately NOT committed — only the generated
assets/portrait.txt is. Point this at a local file when you want to redo it:

    ./scripts/photo_to_ascii.py ~/Desktop/headshot.webp \
        --crop 75,25,435,445 > assets/portrait.txt

Plain luminance is not enough for an outdoor shot: sea and sky sit at roughly
the same brightness as skin. So the subject is segmented on red-minus-blue
(skin and clothing are red-dominant, sky and water are blue-dominant), dark
neutrals like hair and sunglasses are rescued back in, and only the blob
connected to the head survives — that drops rocks, foliage and horizon
speckle. Luminance is then stretched across subject pixels only, so the face
uses the whole character ramp instead of a narrow band of it.
"""

import argparse
import re
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

RAMP = "@%#*+=~:. "  # dense (dark) -> sparse (light)


def build_mask(rgb: np.ndarray, lum: np.ndarray, threshold: float) -> Image.Image:
    r, b = rgb[..., 0], rgb[..., 2]
    subject = np.maximum((r - b) / 255.0, (0.18 - lum) * 3.0)
    mask = Image.fromarray(((subject > threshold) * 255).astype(np.uint8))
    # close pupil-sized holes, then wipe single-pixel speckle
    mask = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    return mask.filter(ImageFilter.MedianFilter(7))


def largest_head_blob(grid: np.ndarray) -> np.ndarray:
    """Flood fill from the first substantial row: the top of the head."""
    height, width = grid.shape
    seed = None
    for y in range(height):
        row = np.flatnonzero(grid[y])
        if row.size >= width // 4:
            seed = (y, int(row.mean()))
            break
    keep = np.zeros_like(grid)
    if seed is None:
        return grid
    keep[seed] = True
    queue = deque([seed])
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width and grid[ny, nx] and not keep[ny, nx]:
                keep[ny, nx] = True
                queue.append((ny, nx))
    return keep


def despeckle(rows: list[str]) -> list[str]:
    """Drop the two artefacts the mask reliably leaves behind.

    A leading run of the lightest ramp characters is haze off the water, never
    the subject; one or two characters marooned after a gap at the end of a
    line are foliage the flood fill reached through a thin bridge.
    """
    cleaned = []
    for line in rows:
        previous = None
        while previous != line:
            previous = line
            line = re.sub(r"^(\s*)([.:]+~?)",
                          lambda m: m.group(1) + " " * len(m.group(2)), line)
        line = re.sub(r"\s+\S{1,2}$", "", line) if len(line.strip()) > 20 else line
        cleaned.append(line.rstrip())
    return cleaned


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--width", type=int, default=44, help="output columns")
    ap.add_argument("--crop", default=None, help="left,top,right,bottom in pixels")
    ap.add_argument("--threshold", type=float, default=0.05,
                    help="subject cutoff; raise to shed background, lower if the face gets holes")
    ap.add_argument("--gamma", type=float, default=1.0)
    ap.add_argument("--aspect", type=float, default=0.5,
                    help="character cell height/width ratio")
    args = ap.parse_args()

    img = Image.open(args.image).convert("RGB")
    if args.crop:
        img = img.crop(tuple(int(v) for v in args.crop.split(",")))

    rgb = np.asarray(img).astype(np.float32)
    lum = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]) / 255.0
    mask = build_mask(rgb, lum, args.threshold)

    inside = lum[np.asarray(mask) > 127]
    if inside.size == 0:
        print("no subject found; try a lower --threshold", file=sys.stderr)
        return 1
    lo, hi = np.percentile(inside, 2), np.percentile(inside, 98)
    shade = np.clip((lum - lo) / max(1e-6, hi - lo), 0, 1) ** args.gamma

    width = args.width
    height = max(1, round(width * img.height / img.width * args.aspect))
    grid = np.asarray(mask.resize((width, height), Image.BILINEAR)) >= 115
    keep = largest_head_blob(grid)
    shade_grid = np.asarray(
        Image.fromarray((shade * 255).astype(np.uint8))
        .resize((width, height), Image.LANCZOS)
    ).astype(np.float32) / 255.0

    scale = len(RAMP) - 1
    rows = [
        "".join(
            RAMP[min(scale, max(0, round(shade_grid[y, x] * scale)))] if keep[y, x] else " "
            for x in range(width)
        ).rstrip()
        for y in range(height)
    ]
    rows = despeckle(rows)
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
