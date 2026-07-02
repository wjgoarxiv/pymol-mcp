"""Generate the pymol-mcp cover image (2560x1280).

Deep blue/teal molecular gradient with a faint clathrate-cage wireframe motif
(pentagons + hexagons = 5^12 / 5^12 6^2 cage faces), bold monospace title, rounded corners.
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 2560, 1280
CORNER_RADIUS = 80

# -- 1. Base canvas (deep navy) ----------------------------------------------
base = Image.new("RGBA", (W, H), (8, 12, 24, 255))  # #080c18


# -- 2. Color blobs (blue / teal / cyan) -------------------------------------
def make_blob(size, color_rgba, cx, cy, rx, ry):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=color_rgba)
    return layer


blobs = [
    # (r, g, b, a,     cx,   cy,   rx,  ry,  blur)
    (14, 116, 144, 200, 700, 620, 720, 520, 130),   # teal, centered-left
    (30, 64, 175, 165, 1950, 240, 620, 430, 110),   # blue, top-right
    (6, 182, 212, 150, 1350, 1160, 900, 360, 95),   # cyan, bottom
    (37, 99, 235, 120, 1500, 640, 520, 360, 85),    # mid blue, center
]
canvas = base.copy()
for r, g, b, a, cx, cy, rx, ry, blur in blobs:
    blob = make_blob((W, H), (r, g, b, a), cx, cy, rx, ry).filter(ImageFilter.GaussianBlur(radius=blur))
    canvas = Image.alpha_composite(canvas, blob)
canvas = canvas.filter(ImageFilter.GaussianBlur(radius=8))


# -- 3. Clathrate-cage wireframe motif (faint pentagons + hexagons) ----------
motif = Image.new("RGBA", (W, H), (0, 0, 0, 0))
mdraw = ImageDraw.Draw(motif)
rng = np.random.default_rng(7)


def polygon(cx, cy, radius, sides, rot, color):
    pts = []
    for k in range(sides):
        ang = rot + 2 * math.pi * k / sides
        pts.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    # edges
    for k in range(sides):
        mdraw.line([pts[k], pts[(k + 1) % sides]], fill=color, width=2)
    # vertices as small nodes
    for px, py in pts:
        mdraw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(150, 220, 235, color[3]))


for _ in range(26):
    cx = float(rng.integers(60, W - 60))
    cy = float(rng.integers(60, H - 60))
    radius = float(rng.integers(45, 105))
    sides = int(rng.choice([5, 6]))            # clathrate cage faces
    rot = float(rng.uniform(0, math.pi))
    alpha = int(rng.integers(28, 70))
    polygon(cx, cy, radius, sides, rot, (120, 200, 220, alpha))

motif = motif.filter(ImageFilter.GaussianBlur(radius=0.6))
canvas = Image.alpha_composite(canvas, motif)


# -- 4. Film grain -----------------------------------------------------------
noise = rng.integers(0, 255, (H, W), dtype=np.uint8)
grain_alpha = (noise * 0.16).astype(np.uint8)
grain = np.stack([noise, noise, noise, grain_alpha], axis=-1).astype(np.uint8)
canvas = Image.alpha_composite(canvas, Image.fromarray(grain, "RGBA"))


# -- 5. Fonts ----------------------------------------------------------------
TITLE_SIZE, SUB_SIZE, TAG_SIZE = 210, 66, 46
try:
    font_title = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", TITLE_SIZE, index=1)
    font_sub = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", SUB_SIZE, index=0)
    font_tag = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", TAG_SIZE, index=0)
except Exception:
    font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New Bold.ttf", TITLE_SIZE)
    font_sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New Bold.ttf", SUB_SIZE)
    font_tag = font_sub

TITLE = "pymol-mcp"
SUB = "Headless PyMOL for MD & clathrate-hydrate science."
TAG = "GROMACS  •  LAMMPS  •  cages  •  F3/F4  •  H-bonds"


def measure(text, font):
    b = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=font)
    return b


tb = measure(TITLE, font_title)
t_w, t_h = tb[2] - tb[0], tb[3] - tb[1]
sb = measure(SUB, font_sub)
s_w, s_h = sb[2] - sb[0], sb[3] - sb[1]
gb = measure(TAG, font_tag)
g_w = gb[2] - gb[0]

GAP1, GAP2 = 44, 30
total_h = t_h + GAP1 + s_h + GAP2 + (gb[3] - gb[1])
block_top = (H - total_h) // 2 - 20

title_x = (W - t_w) // 2 - tb[0]
title_y = block_top - tb[1]
sub_x = (W - s_w) // 2 - sb[0]
sub_y = title_y + t_h + GAP1
tag_x = (W - g_w) // 2 - gb[0]
tag_y = sub_y + s_h + GAP2


def text_layer(text, x, y, font, color):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((x, y), text, font=font, fill=color)
    return layer


# -- 6. Title with cyan glow -------------------------------------------------
for color, blur_r in [((34, 211, 238, 70), 20), ((56, 189, 248, 95), 10), ((125, 211, 252, 120), 4)]:
    glow = text_layer(TITLE, title_x, title_y, font_title, color).filter(ImageFilter.GaussianBlur(radius=blur_r))
    canvas = Image.alpha_composite(canvas, glow)
canvas = Image.alpha_composite(canvas, text_layer(TITLE, title_x, title_y, font_title, (255, 255, 255, 248)))

# -- 7. Subtitle + tagline ---------------------------------------------------
canvas = Image.alpha_composite(canvas, text_layer(SUB, sub_x, sub_y, font_sub, (196, 216, 232, 220)))
canvas = Image.alpha_composite(canvas, text_layer(TAG, tag_x, tag_y, font_tag, (120, 200, 220, 200)))

# -- 8. Rounded corners + polish --------------------------------------------
mask = Image.new("L", (W, H), 0)
ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (W - 1, H - 1)], radius=CORNER_RADIUS, fill=255)
canvas.putalpha(mask)
canvas = canvas.filter(ImageFilter.GaussianBlur(radius=1))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cover.png")
canvas.save(out, "PNG", dpi=(300, 300))
print(f"Saved: {out}  size={canvas.size} mode={canvas.mode}")
