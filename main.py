from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from gem12_screen import Gem12Screen, ScreenError, find_screen_port


DEFAULT_IMAGE = (
    Path(__file__).resolve().parent
    / "assets"
    / "backgrounds"
    / "background-01.jpg"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="控制 AOOSTAR GEM12 960x376 屏幕")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE, help="要显示的图片")
    parser.add_argument("--port", help="指定串口，但仍会校验设备 VID/PID")
    parser.add_argument("--open-only", action="store_true", help="只发送开屏命令，不传图")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        port = find_screen_port(args.port)
        with Gem12Screen(port) as screen:
            ack = screen.open_screen()
            print(f"已向 {port} 发送开屏命令，响应: {ack.hex(' ') or '无'}")

            if args.open_only:
                return 0

            with Image.open(args.image) as source_image:
                image = source_image.convert("RGB")
            packet_count = screen.show_image(image)
            print(f"已显示 {args.image}：960x376，发送 {packet_count} 个数据块")
            return 0
    except (OSError, ScreenError, ValueError) as exc:
        print(f"控制失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
