"""用模拟数值演示动态仪表；不采集机器硬件数据。"""

from time import perf_counter, sleep

from PIL import Image, ImageDraw, ImageFont

from gem12_screen import Screen


LABEL_FONT = ImageFont.load_default(size=28)
VALUE_FONT = ImageFont.load_default(size=56)
VALUES = [(100, 16384), (9, 1), (0, 8192), (67, 9), (1, 32768), (0, 1), (0, 1)]


def make_dashboard(cpu_percent: int, memory_mb: int) -> Image.Image:
    image = Image.new("RGB", (960, 376), "#17212b")
    draw = ImageDraw.Draw(image)
    draw.text((60, 25), "SIMULATED DASHBOARD", font=LABEL_FONT, fill="white")
    draw.text((60, 100), "CPU LOAD", font=LABEL_FONT, fill="white")
    draw.text((520, 100), "MEMORY USED", font=LABEL_FONT, fill="white")
    draw.text((60, 140), f"{cpu_percent}%", font=VALUE_FONT, fill="#40df80")
    draw.text((520, 140), f"{memory_mb} MB", font=VALUE_FONT, fill="#ffd75a")
    draw.rectangle((60, 225, 440, 250), outline="white", width=2)
    if cpu_percent:
        draw.rectangle((63, 228, 63 + int(cpu_percent * 3.74), 247), fill="#40df80")
    draw.text((60, 320), "DEMO VALUES - NOT ACTUAL HARDWARE READINGS", font=LABEL_FONT, fill="white")
    return image


def main() -> None:
    with Screen.connect() as screen:
        for cpu_percent, memory_mb in VALUES * 4:
            started = perf_counter()
            blocks = screen.show(make_dashboard(cpu_percent, memory_mb))
            print(f"模拟 CPU {cpu_percent}% / 内存 {memory_mb} MB：发送 {blocks} 块")
            sleep(max(0, 0.5 - (perf_counter() - started)))


if __name__ == "__main__":
    main()
