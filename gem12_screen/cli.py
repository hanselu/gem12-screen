from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .screen import Screen, ScreenError


DEFAULT_IMAGE = Path(__file__).resolve().parent / "assets" / "example_images" / "01.jpg"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="控制 AOOSTAR GEM12 960x376 屏幕")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE, help="要显示的图片")
    parser.add_argument("--port", help="指定串口，但仍会校验设备 VID/PID")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--open-only", action="store_true", help="只发送开屏命令，不传图")
    mode.add_argument("--turn-off", action="store_true", help="发送关屏命令")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with Screen.connect(args.port, wake=not args.turn_off) as screen:
            print(f"已连接屏幕：{screen.port}")
            if args.turn_off:
                screen.turn_off()
                print("屏幕已关闭")
                return 0
            if args.open_only:
                return 0
            packet_count = screen.show(args.image)
            print(f"已显示 {args.image}：960x376，发送 {packet_count} 个数据块")
            return 0
    except ScreenError as exc:
        print(f"控制失败：{exc}", file=sys.stderr)
        return 1
