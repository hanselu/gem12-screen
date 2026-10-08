"""独立监听指纹轻触，只打印通知，不连接或操作屏幕。"""

import argparse
import logging

from gem12_touch import FingerprintTouch, TouchError


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="打印回调计数及退出步骤的耗时")
    args = parser.parse_args(argv)
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
    try:
        with FingerprintTouch.connect() as touch:
            print(f"已监听指纹设备 {touch.unit_id}，轻触后放开手指；按 Ctrl+C 退出。", flush=True)
            count = 0
            try:
                while True:
                    event = touch.read(timeout=0.5)
                    if event is None:
                        continue
                    if event.reject_detail:
                        print(f"采样未成功：RejectDetail={event.reject_detail}", flush=True)
                        continue
                    count += 1
                    print(f"轻触通知 #{count}，设备 {event.unit_id}，通知时间 {event.timestamp:.3f}", flush=True)
            except KeyboardInterrupt:
                print("正在关闭监听，等待 Windows 释放会话……", flush=True)
        print("监听已关闭。", flush=True)
    except KeyboardInterrupt:
        print("操作被中断，监听清理状态未确认。", flush=True)
    except TouchError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
