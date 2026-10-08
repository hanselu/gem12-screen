from __future__ import annotations

import unittest
from unittest.mock import patch

import serial
from PIL import Image

from gem12_screen import Screen, ScreenError
from gem12_screen._protocol import (
    DATA_HEADER,
    FRAME_END,
    FRAME_START,
    OPEN_SCREEN,
    TURN_OFF_SCREEN,
    encode_rgb565_le,
)


class FakeSerial:
    def __init__(self, response: bytes = b"A") -> None:
        self.response = response
        self.is_open = True
        self.writes: list[bytes] = []
        self.closed = False
        self.pending = bytearray()
        self.fail_write_after: int | None = None
        self.zero_write_after: int | None = None
        self.fail_flush = False
        self.fail_read = False
        self.max_write_size: int | None = None

    @property
    def in_waiting(self) -> int:
        return len(self.pending)

    def reset_input_buffer(self) -> None:
        self.pending.clear()

    def write(self, data: bytes) -> int:
        if self.fail_write_after is not None and len(self.writes) >= self.fail_write_after:
            raise serial.SerialException("模拟发送失败")
        if self.zero_write_after is not None and len(self.writes) >= self.zero_write_after:
            return 0
        count = min(len(data), self.max_write_size or len(data))
        written = bytes(data[:count])
        self.writes.append(written)
        if written in (OPEN_SCREEN, TURN_OFF_SCREEN):
            self.pending.extend(self.response)
        elif written.startswith(DATA_HEADER) or written == FRAME_END:
            self.pending.extend(b"A")
        return count

    def flush(self) -> None:
        if self.fail_flush:
            raise serial.SerialException("模拟 flush 失败")

    def read(self, size: int) -> bytes:
        if self.fail_read:
            raise serial.SerialException("模拟读取失败")
        response = bytes(self.pending[:size])
        del self.pending[:size]
        return response

    def close(self) -> None:
        self.is_open = False
        self.closed = True


class ScreenTests(unittest.TestCase):
    def test_partial_update_preserves_offsets_and_reconstructs_frame(self) -> None:
        connection = FakeSerial()
        screen = Screen("FAKE", connection)
        original = Image.new("RGB", (960, 376), "black")
        screen.show(original)
        connection.writes.clear()

        updated = original.copy()
        for position in ((0, 0), (23, 0), (12, 205), (959, 375)):
            updated.putpixel(position, (255, 255, 255))
        self.assertEqual(screen.show(updated), 5)

        reconstructed = bytearray(encode_rgb565_le(original))
        offsets = []
        self.assertEqual(connection.writes[0], FRAME_START)
        self.assertEqual(connection.writes[-1], FRAME_END)
        for packet in connection.writes[1:-1]:
            self.assertEqual(packet[:8], DATA_HEADER)
            offset = int.from_bytes(packet[8:12], "little")
            offsets.append(offset)
            reconstructed[offset:offset + len(packet) - 12] = packet[12:]
        remote_offset = (205 * 960 + 12) * 2
        remote_chunk = remote_offset // 47 * 47
        self.assertEqual(offsets, [0, 47, remote_chunk, remote_chunk + 47, 960 * 376 * 2 - 47])
        self.assertEqual(reconstructed, encode_rgb565_le(updated))

    def test_identical_rgb565_frame_sends_no_image_blocks(self) -> None:
        connection = FakeSerial()
        screen = Screen("FAKE", connection)
        screen.show(Image.new("RGB", (960, 376), "black"))
        connection.writes.clear()

        self.assertEqual(screen.show(Image.new("RGB", (960, 376), (1, 1, 1))), 0)
        self.assertEqual(connection.writes, [FRAME_START, FRAME_END])

    def test_force_full_refresh_then_returns_to_partial_updates(self) -> None:
        screen = Screen("FAKE", FakeSerial())
        image = Image.new("RGB", (960, 376), "red")
        self.assertEqual(screen.show(image), 15360)
        self.assertEqual(screen.show(image, force_full=True), 15360)
        self.assertEqual(screen.show(image), 0)

    def test_transfer_errors_require_full_refresh_on_next_show(self) -> None:
        for failure in ("write", "zero_write", "flush", "read"):
            with self.subTest(failure=failure):
                connection = FakeSerial()
                screen = Screen("FAKE", connection)
                screen.show(Image.new("RGB", (960, 376), "black"))
                connection.writes.clear()
                if failure == "write":
                    connection.max_write_size = 31
                    connection.fail_write_after = 2
                elif failure == "zero_write":
                    connection.zero_write_after = 2
                elif failure == "flush":
                    connection.fail_flush = True
                else:
                    connection.fail_read = True
                changed = Image.new("RGB", (960, 376), "black")
                changed.putpixel((23, 0), (255, 255, 255))
                with self.assertRaises(ScreenError):
                    screen.show(changed)

                connection.fail_write_after = None
                connection.zero_write_after = None
                connection.fail_flush = False
                connection.fail_read = False
                connection.max_write_size = None
                self.assertEqual(screen.show(changed), 15360)

    def test_control_commands_invalidate_frame_cache(self) -> None:
        for action in ("wake", "turn_off"):
            with self.subTest(action=action):
                screen = Screen("FAKE", FakeSerial())
                image = Image.new("RGB", (960, 376), "black")
                screen.show(image)
                getattr(screen, action)()
                self.assertEqual(screen.show(image), 15360)

    def test_frame_responses_are_consumed_after_each_show(self) -> None:
        connection = FakeSerial()
        screen = Screen("FAKE", connection)
        for color in ("black", "red", "green", "blue", "blue"):
            screen.show(Image.new("RGB", (960, 376), color))
            self.assertEqual(connection.in_waiting, 0)

    @patch("gem12_screen.screen.serial.Serial")
    @patch("gem12_screen.screen._find_screen_port", return_value="COM3")
    def test_new_connection_always_starts_with_full_frame(self, find_port, serial_class) -> None:
        serial_class.side_effect = [FakeSerial(), FakeSerial()]
        image = Image.new("RGB", (960, 376), "black")
        with Screen.connect(wake=False) as first:
            self.assertEqual(first.show(image), 15360)
            self.assertEqual(first.show(image), 0)
        with Screen.connect(wake=False) as second:
            self.assertEqual(second.show(image), 15360)

    def test_invalid_image_does_not_discard_successful_frame(self) -> None:
        screen = Screen("FAKE", FakeSerial())
        image = Image.new("RGB", (960, 376), "black")
        screen.show(image)
        with patch.object(screen, "_load_image", side_effect=ScreenError("模拟图片读取失败")):
            with self.assertRaises(ScreenError):
                screen.show("missing.png")
        self.assertEqual(screen.show(image), 0)

    def test_short_writes_still_send_complete_frame(self) -> None:
        connection = FakeSerial()
        connection.max_write_size = 31
        screen = Screen("FAKE", connection)
        self.assertEqual(screen.show(Image.new("RGB", (960, 376), "black")), 15360)
        wire = b"".join(connection.writes)
        self.assertEqual(len(wire), 906264)
        self.assertTrue(wire.startswith(FRAME_START))
        self.assertTrue(wire.endswith(FRAME_END))

    @patch("gem12_screen.screen.serial.Serial")
    @patch("gem12_screen.screen._find_screen_port", return_value="COM3")
    def test_public_api_connects_and_sends_image(self, find_port, serial_class) -> None:
        connection = FakeSerial()
        serial_class.return_value = connection

        with Screen.connect() as screen:
            packet_count = screen.show(Image.new("RGB", (960, 376), "red"))

        self.assertEqual(screen.port, "COM3")
        self.assertEqual(packet_count, 15_360)
        self.assertEqual(connection.writes[0], OPEN_SCREEN)
        self.assertEqual(connection.writes[1], FRAME_START)
        self.assertEqual(connection.writes[-1], FRAME_END)
        self.assertTrue(connection.closed)
        find_port.assert_called_once_with(None)

    @patch("gem12_screen.screen.serial.Serial")
    @patch("gem12_screen.screen._find_screen_port", return_value="COM3")
    def test_connect_closes_port_when_ack_is_missing(self, find_port, serial_class) -> None:
        connection = FakeSerial(response=b"")
        serial_class.return_value = connection

        with self.assertRaisesRegex(ScreenError, "没有返回预期响应"):
            Screen.connect()

        self.assertTrue(connection.closed)

    @patch("gem12_screen.screen.serial.Serial")
    @patch("gem12_screen.screen._find_screen_port", return_value="COM3")
    def test_turn_off_can_connect_without_waking_screen(self, find_port, serial_class) -> None:
        connection = FakeSerial()
        serial_class.return_value = connection

        with Screen.connect(wake=False) as screen:
            screen.turn_off()

        self.assertEqual(connection.writes, [TURN_OFF_SCREEN])
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
