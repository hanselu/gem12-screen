from __future__ import annotations

from collections.abc import Iterator
from types import TracebackType

import serial
from PIL import Image
from serial.tools import list_ports

SCREEN_VID = 0x0416
SCREEN_PID = 0x90A1
SCREEN_WIDTH = 960
SCREEN_HEIGHT = 376
BAUD_RATE = 1_500_000
DATA_CHUNK_SIZE = 47

OPEN_SCREEN = bytes.fromhex("AA55AA550B000000")
FRAME_START = bytes.fromhex("AA55AA550500000004000F2F00040B00")
DATA_HEADER = bytes.fromhex("AA55AA5508000000")
FRAME_END = bytes.fromhex("AA55AA5506000000")


class ScreenError(RuntimeError):
    pass


def _is_screen_port(port: object) -> bool:
    return getattr(port, "vid", None) == SCREEN_VID and getattr(port, "pid", None) == SCREEN_PID


def find_screen_port(requested_port: str | None = None) -> str:
    matches = [port.device for port in list_ports.comports() if _is_screen_port(port)]
    if not matches:
        raise ScreenError(f"未找到 USB 设备 VID_{SCREEN_VID:04X}&PID_{SCREEN_PID:04X}")

    if requested_port is not None:
        for device in matches:
            if device.casefold() == requested_port.casefold():
                return device
        raise ScreenError(f"{requested_port} 不是目标屏幕串口；检测到：{', '.join(matches)}")

    if len(matches) > 1:
        raise ScreenError(f"检测到多个目标屏幕串口，请用 --port 指定：{', '.join(matches)}")
    return matches[0]


def prepare_image(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    if image.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
        image = image.resize((SCREEN_WIDTH, SCREEN_HEIGHT), Image.Resampling.LANCZOS)
    return image


def encode_rgb565_le(image: Image.Image) -> bytes:
    rgb = image.convert("RGB").tobytes()
    encoded = bytearray(len(rgb) // 3 * 2)
    output_index = 0
    for input_index in range(0, len(rgb), 3):
        red, green, blue = rgb[input_index : input_index + 3]
        pixel = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        encoded[output_index] = pixel & 0xFF
        encoded[output_index + 1] = pixel >> 8
        output_index += 2
    return bytes(encoded)


def iter_data_packets(image_data: bytes) -> Iterator[bytes]:
    for offset in range(0, len(image_data), DATA_CHUNK_SIZE):
        payload = image_data[offset : offset + DATA_CHUNK_SIZE]
        yield DATA_HEADER + offset.to_bytes(4, "little") + payload


class Gem12Screen:
    def __init__(self, port: str) -> None:
        self.port = port
        self._serial: serial.Serial | None = None

    def __enter__(self) -> Gem12Screen:
        self._serial = serial.Serial(
            self.port,
            baudrate=BAUD_RATE,
            timeout=1,
            write_timeout=10,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def _connection(self) -> serial.Serial:
        if self._serial is None or not self._serial.is_open:
            raise ScreenError("串口尚未打开")
        return self._serial

    def _write_exact(self, data: bytes) -> None:
        connection = self._connection()
        sent = 0
        while sent < len(data):
            count = connection.write(data[sent:])
            if count is None or count <= 0:
                raise ScreenError("串口写入未取得进展")
            sent += count

    def open_screen(self) -> bytes:
        connection = self._connection()
        connection.reset_input_buffer()
        self._write_exact(OPEN_SCREEN)
        connection.flush()
        return connection.read(16)

    def show_image(self, image: Image.Image) -> int:
        image_data = encode_rgb565_le(prepare_image(image))
        expected_size = SCREEN_WIDTH * SCREEN_HEIGHT * 2
        if len(image_data) != expected_size:
            raise ScreenError(f"图像编码长度异常：{len(image_data)}，预期 {expected_size}")

        self._write_exact(FRAME_START)
        packet_count = 0
        for packet in iter_data_packets(image_data):
            self._write_exact(packet)
            packet_count += 1
        self._write_exact(FRAME_END)
        self._connection().flush()
        return packet_count
