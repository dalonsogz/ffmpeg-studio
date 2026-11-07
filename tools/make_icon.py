"""Genera el icono de la aplicación (assets/icon.ico) sin dependencias externas."""

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "icon.ico")
SIZE = 256

image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)

# Fondo redondeado con degradado vertical (verde de la marca).
for y in range(8, SIZE - 8):
    ratio = (y - 8) / (SIZE - 16)
    r = int(52 + (16 - 52) * ratio)
    g = int(211 + (185 - 211) * ratio)
    b = int(153 + (129 - 153) * ratio)
    draw.line([(8, y), (SIZE - 8, y)], fill=(r, g, b, 255))

mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=58, fill=255)
image.putalpha(mask)

# Triángulo de reproducción.
draw.polygon([(102, 74), (102, 182), (190, 128)], fill=(240, 255, 248, 255))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
image.save(
    OUT,
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("icono generado:", OUT, os.path.getsize(OUT), "bytes")
