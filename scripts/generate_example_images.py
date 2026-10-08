"""自行绘制 960×376 示例图及总览图，采用项目的 0BSD 许可证。

仅使用数学公式、几何图形和 Pillow 内置字体，不读取外部素材。
重新运行会覆盖包内的 01.jpg～09.jpg 和 docs/example_images_preview.jpg。
"""

import colorsys
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SIZE = (960, 376)
TITLES = (
    "GRADIENT", "COLOR BARS", "ALIGNMENT", "COLOR ORBITS", "LANDSCAPE",
    "WAVES", "CHECKERBOARD", "SIMULATED DASHBOARD", "GEOMETRY",
)


def create_image(number: int) -> Image.Image:
    image = Image.new("RGB", SIZE, "#101925")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    large_font = ImageFont.load_default(size=44)

    if number == 1:
        for x in range(SIZE[0]):
            color = colorsys.hsv_to_rgb(0.48 + 0.42 * x / 959, 0.75, 0.9)
            for y in range(SIZE[1]):
                brightness = 0.35 + 0.65 * (1 - y / 375)
                image.putpixel((x, y), tuple(round(c * brightness * 255) for c in color))
        draw.rounded_rectangle((40, 112, 604, 258), radius=20, fill="#142030")
        draw.text((64, 128), "GEM12 SCREEN", font=large_font, fill="white")
        draw.text((66, 198), "960 x 376  /  USB SERIAL DISPLAY", font=font, fill="#82dce2")
    elif number == 2:
        colors = ("#ffffff", "#ffff00", "#00ffff", "#00ff00", "#ff00ff", "#ff0000", "#0000ff", "#000000")
        for index, color in enumerate(colors):
            left = index * 120
            draw.rectangle((left, 70, left + 119, 255), fill=color)
        for index in range(32):
            level = round(index * 255 / 31)
            draw.rectangle((index * 30, 270, index * 30 + 29, 325), fill=(level,) * 3)
        draw.text((24, 337), "WHITE / YELLOW / CYAN / GREEN / MAGENTA / RED / BLUE / BLACK", font=font, fill="white")
    elif number == 3:
        for x in range(0, 960, 24):
            draw.line((x, 0, x, 375), fill="#34485d", width=1)
        for y in range(0, 376, 24):
            draw.line((0, y, 959, y), fill="#34485d", width=1)
        draw.rectangle((0, 0, 959, 375), outline="white", width=2)
        draw.line((480, 60, 480, 335), fill="#ffd166", width=2)
        draw.line((24, 188, 935, 188), fill="#ffd166", width=2)
        for x, y, color in ((28, 80, "#f15b6c"), (932, 80, "#fbbf24"), (28, 344, "#4ade80"), (932, 344, "#38bdf8")):
            draw.ellipse((x - 16, y - 16, x + 16, y + 16), fill=color)
        draw.ellipse((418, 126, 542, 250), outline="white", width=2)
    elif number == 4:
        for index in range(18):
            radius = 14 + index * 10
            color = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(index / 18, 0.72, 0.95))
            for center_x in (236, 724):
                draw.arc((center_x - radius, 220 - radius, center_x + radius, 220 + radius), 10 + index * 9, 270 + index * 3, fill=color, width=5)
        draw.line((438, 220, 522, 220), fill="white", width=3)
    elif number == 5:
        for y in range(376):
            blend = y / 375
            color = tuple(round(a + (b - a) * blend) for a, b in zip((38, 48, 106), (250, 163, 111)))
            draw.line((0, y, 959, y), fill=color)
        draw.ellipse((720, 85, 826, 191), fill="#ffe3a1")
        draw.polygon(((0, 270), (172, 98), (365, 278), (552, 126), (804, 306), (960, 190), (960, 376), (0, 376)), fill="#68698f")
        draw.polygon(((0, 340), (120, 220), (302, 320), (448, 216), (684, 354), (910, 234), (960, 302), (960, 376), (0, 376)), fill="#354663")
        draw.polygon(((0, 354), (200, 304), (398, 376), (740, 304), (960, 346), (960, 376), (0, 376)), fill="#162e42")
    elif number == 6:
        for index in range(12):
            color = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(0.45 + index * 0.03, 0.7, 0.9))
            points = [(x, round(225 + 68 * math.sin(x / 120 + index * 0.12) + (index - 6) * 7)) for x in range(960)]
            draw.line(points, fill=color, width=4)
        draw.text((36, 82), "CONTINUOUS COLOR", font=large_font, fill="white")
    elif number == 7:
        for index, tile in enumerate((8, 16, 32)):
            start = index * 320
            for y in range(96, 352, tile):
                for x in range(start, start + 320, tile):
                    color = "#f5f5f5" if ((x - start) // tile + (y - 96) // tile) % 2 == 0 else "#172434"
                    draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=color)
            draw.text((start + 16, 64), f"{tile} PX", font=font, fill="#a4c8f0")
    elif number == 8:
        for x, name, value, fraction, color in ((24, "CPU", "42%", 0.42, "#38bdf8"), (336, "MEMORY", "8.0 GB", 0.5, "#a78bfa"), (648, "POWER", "18 W", 0.3, "#fbbf24")):
            draw.rounded_rectangle((x, 86, x + 288, 298), radius=16, fill="#1c2a3c", outline="#354b64", width=2)
            draw.text((x + 20, 106), name, font=font, fill="#a8bbce")
            draw.text((x + 20, 154), value, font=large_font, fill="white")
            draw.rounded_rectangle((x + 20, 244, x + 268, 260), radius=8, fill="#344457")
            draw.rounded_rectangle((x + 20, 244, x + 20 + round(248 * fraction), 260), radius=8, fill=color)
        draw.text((26, 324), "EXAMPLE VALUES  /  NO HARDWARE DATA COLLECTED", font=font, fill="#8fa9c4")
    else:
        palette = ("#38bdf8", "#a78bfa", "#fb7185", "#fbbf24", "#2dd4bf")
        for row in range(3):
            for column in range(8):
                x, y = 76 + column * 112, 124 + row * 78
                color = palette[(row + column) % len(palette)]
                draw.polygon(((x, y - 28), (x + 43, y - 6), (x, y + 16), (x - 43, y - 6)), fill=color)
                draw.polygon(((x - 43, y - 6), (x, y + 16), (x, y + 44), (x - 43, y + 22)), fill="#314863")
                draw.polygon(((x, y + 16), (x + 43, y - 6), (x + 43, y + 22), (x, y + 44)), fill="#1c3048")

    draw.rectangle((16, 12, 670, 52), fill="#101925")
    draw.text((28, 21), f"{number:02}  /  {TITLES[number - 1]}  /  960 x 376", font=font, fill="white")
    return image


def main() -> None:
    destination = ROOT / "gem12_screen/assets/example_images"
    destination.mkdir(parents=True, exist_ok=True)
    preview = Image.new("RGB", (1008, 1144), "#101925")
    preview_draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default(size=15)
    for number in range(1, 10):
        with create_image(number) as image:
            path = destination / f"{number:02}.jpg"
            image.save(path, quality=95, subsampling=0, optimize=True)
            x = 16 + ((number - 1) % 2) * 496
            y = 16 + ((number - 1) // 2) * 224
            with image.resize((480, 188), Image.Resampling.LANCZOS) as thumbnail:
                preview.paste(thumbnail, (x, y))
            preview_draw.text((x, y + 194), f"{number:02}.jpg  /  {TITLES[number - 1]}", font=font, fill="white")
            print(path.relative_to(ROOT))
    preview_path = ROOT / "docs/example_images_preview.jpg"
    preview.save(preview_path, quality=95, subsampling=0, optimize=True)
    preview.close()
    print(preview_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
