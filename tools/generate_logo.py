from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent

SIZE = 512
BG = (30, 31, 38, 255)       # #1e1f26 - app dark background
ACCENT = (237, 28, 36, 255)  # #ed1c24 - trakt red
WHITE = (245, 245, 247, 255)

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

margin = 24
draw.rounded_rectangle([margin, margin, SIZE - margin, SIZE - margin], radius=110, fill=BG)

# main play-button circle
cx, cy = SIZE // 2, SIZE // 2 - 12
r = 172
draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)

# white play triangle, optically centered inside the circle
tri_w, tri_h = 132, 164
x0 = cx - tri_w * 0.32
points = [
    (x0, cy - tri_h / 2),
    (x0, cy + tri_h / 2),
    (x0 + tri_w, cy),
]
draw.polygon(points, fill=WHITE)

# "checked in" badge, bottom-right corner
badge_r = 92
bx = SIZE - margin - badge_r - 6
by = SIZE - margin - badge_r - 6
draw.ellipse([bx - badge_r - 6, by - badge_r - 6, bx + badge_r + 6, by + badge_r + 6], fill=BG)
draw.ellipse([bx - badge_r, by - badge_r, bx + badge_r, by + badge_r], fill=WHITE)
draw.line(
    [(bx - 46, by + 6), (bx - 10, by + 42), (bx + 56, by - 46)],
    fill=ACCENT, width=24, joint="curve",
)

img.save(OUT / "logo.png")
img.resize((256, 256), Image.LANCZOS).save(
    OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
)
print("saved logo.png and icon.ico")
