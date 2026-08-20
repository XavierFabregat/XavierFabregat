#!/usr/bin/env -S uv run --quiet --with pillow --with numpy python
"""Cut the subject out of a photo, leaving the background transparent.

The card generator converts an image to ASCII itself and renders transparent
pixels as spaces, but its own background removal looks for a single solid
colour. An outdoor photo has a gradient sky and sea, so that fails and the
whole frame gets drawn. This does the separation properly first, reusing the
red-minus-blue approach: skin and clothing are red-dominant, sky and water are
blue-dominant, dark neutrals like hair and sunglasses are rescued back in, and
only the region connected to the head survives.

    ./scripts/cutout.py ~/Desktop/headshot.webp --crop 100,20,400,400 \
        --out assets/portrait.png
"""

import argparse
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


def build_mask(rgb: np.ndarray, lum: np.ndarray, threshold: float) -> Image.Image:
    r, b = rgb[..., 0], rgb[..., 2]
    subject = np.maximum((r - b) / 255.0, (0.18 - lum) * 3.0)
    mask = Image.fromarray(((subject > threshold) * 255).astype(np.uint8))
    mask = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    return mask.filter(ImageFilter.MedianFilter(7))


def largest_head_blob(grid: np.ndarray) -> np.ndarray:
    """Flood fill from the first substantial row, which is the top of the head."""
    height, width = grid.shape
    seed = None
    for y in range(height):
        row = np.flatnonzero(grid[y])
        if row.size >= width // 4:
            seed = (y, int(row.mean()))
            break
    if seed is None:
        return grid
    keep = np.zeros_like(grid)
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out", required=True)
    ap.add_argument("--crop", default=None, help="left,top,right,bottom in pixels")
    ap.add_argument("--threshold", type=float, default=0.05)
    ap.add_argument("--feather", type=float, default=1.2,
                    help="blur radius on the mask edge, in pixels")
    ap.add_argument("--brightness", type=float, default=1.0,
                    help="the card draws each character in its source pixel's colour, so "
                         "skin tones read as muddy on a dark card; lift them here")
    ap.add_argument("--saturation", type=float, default=1.0)
    args = ap.parse_args()

    img = Image.open(args.image).convert("RGB")
    if args.crop:
        img = img.crop(tuple(int(v) for v in args.crop.split(",")))

    rgb = np.asarray(img).astype(np.float32)
    lum = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]) / 255.0

    chroma = np.abs(rgb[..., 0] - rgb[..., 2]).mean()
    if chroma < 2.0:
        print(f"{args.image} is greyscale (mean |r-b| = {chroma:.2f}); there is no "
              "colour to separate the subject from the background.", file=sys.stderr)
        return 1

    mask = build_mask(rgb, lum, args.threshold)
    keep = largest_head_blob(np.asarray(mask) > 127)
    alpha = Image.fromarray((keep * 255).astype(np.uint8))
    if args.feather > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(args.feather))

    out = img.copy()
    if args.brightness != 1.0:
        out = ImageEnhance.Brightness(out).enhance(args.brightness)
    if args.saturation != 1.0:
        out = ImageEnhance.Color(out).enhance(args.saturation)
    out.putalpha(alpha)
    out.save(args.out, "PNG", optimize=True)

    covered = float(np.asarray(alpha).mean() / 255)
    print(f"wrote {args.out}  {out.size[0]}x{out.size[1]}  "
          f"subject covers {covered:.0%} of the frame")
    return 0


if __name__ == "__main__":
    sys.exit(main())
