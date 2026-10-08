from pathlib import Path

from gem12_screen import Screen


IMAGE = (
    Path(__file__).resolve().parents[1]
    / "gem12_screen"
    / "assets"
    / "example_images"
    / "02.jpg"
)


with Screen.connect() as screen:
    screen.show(IMAGE)
    print(f"图片已显示到 {screen.port}")
