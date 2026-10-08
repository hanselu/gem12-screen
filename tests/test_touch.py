from __future__ import annotations

import ctypes as c
from contextlib import redirect_stdout
from io import StringIO
import subprocess
import sys
import unittest
from unittest.mock import patch

from gem12_touch import FingerprintTouch, TouchError
from gem12_touch.touch import (
    DWORD, EVENT_ERROR, FP_UNCLAIMED, _ErrorEvent, _Unclaimed, _UnitSchema, _pending_cleanup,
)


FAIL = -2147467259


class FakeWinBio:
    def __init__(self, devices=("USB\\VID_3274&PID_8012\\TEST",)) -> None:
        self.units = (_UnitSchema * len(devices))()
        for i, device in enumerate(devices):
            self.units[i].unit_id = i + 3
            self.units[i].device_instance = device
        self.calls = []
        self.freed = []
        self.callback = None
        self.fail_register = False
        self.fail_unregister = False
        self.fail_close = False
        self.event_on_register = False

    def WinBioEnumBiometricUnits(self, factor, pointer, count):
        self.calls.append("enum")
        c.cast(pointer, c.POINTER(c.POINTER(_UnitSchema)))[0] = c.cast(self.units, c.POINTER(_UnitSchema))
        count._obj.value = len(self.units)
        return 0

    def WinBioFree(self, pointer):
        self.freed.append(c.cast(pointer, c.c_void_p).value)

    def WinBioOpenSession(self, factor, pool, flags, units, count, database, session):
        self.calls.append("open")
        session._obj.value = 42
        return 0

    def WinBioRegisterEventMonitor(self, session, mask, callback, context):
        self.calls.append("register")
        if self.fail_register:
            return FAIL
        self.callback = callback
        if self.event_on_register:
            self.emit(_Unclaimed(FP_UNCLAIMED, 3, 0))
        return 0

    def WinBioUnregisterEventMonitor(self, session):
        self.calls.append("unregister")
        return FAIL if self.fail_unregister else 0

    def WinBioCloseSession(self, session):
        self.calls.append("close")
        return FAIL if self.fail_close else 0

    def emit(self, event=None, status=0):
        pointer = c.addressof(event) if event is not None else None
        self.callback(None, status, pointer)
        return pointer


class TouchTests(unittest.TestCase):
    def connect(self, api):
        with patch("gem12_touch.touch._load_api", return_value=api):
            return FingerprintTouch.connect()

    def test_immediate_and_queued_notices_keep_order_and_free_memory(self):
        api = FakeWinBio()
        api.event_on_register = True
        with self.connect(api) as touch:
            self.assertTrue(touch.is_connected)
            pointers = [api.emit(_Unclaimed(FP_UNCLAIMED, 3, detail)) for detail in (0, 7, 0)]
            notices = [touch.read(timeout=0) for _ in range(4)]
            self.assertEqual([e.reject_detail for e in notices], [0, 0, 7, 0])
            self.assertEqual([e.unit_id for e in notices], [3] * 4)
            self.assertEqual([e.timestamp for e in notices], sorted(e.timestamp for e in notices))
            self.assertIsNone(touch.read(timeout=0))
            for pointer in pointers:
                self.assertIn(pointer, api.freed)
        self.assertFalse(touch.is_connected)
        self.assertEqual(api.calls, ["open", "enum", "register", "unregister", "close"])
        touch.close()
        self.assertEqual(api.calls.count("close"), 1)
        with self.assertRaises(TouchError):
            touch.read(timeout=0)

    def test_other_devices_and_unknown_events_are_freed_without_touch(self):
        api = FakeWinBio()
        with self.connect(api) as touch:
            pointers = [api.emit(_Unclaimed(FP_UNCLAIMED, 9, 0)), api.emit(DWORD(123))]
            with self.assertLogs("gem12_touch.touch", level="DEBUG") as logs:
                self.assertIsNone(touch.read(timeout=0.001))
            self.assertIn("目标设备=3，最近忽略设备=9", "\n".join(logs.output))
            self.assertTrue(all(p in api.freed for p in pointers))

    def test_callback_errors_reach_reader_and_event_memory_is_freed(self):
        api = FakeWinBio()
        with self.connect(api) as touch:
            pointer = api.emit(_Unclaimed(FP_UNCLAIMED, 3, 0), status=FAIL)
            with self.assertRaisesRegex(TouchError, "80004005"):
                touch.read(timeout=0)
            self.assertIn(pointer, api.freed)
            pointer = api.emit(_ErrorEvent(EVENT_ERROR, FAIL))
            with self.assertRaisesRegex(TouchError, "80004005"):
                touch.read(timeout=0)
            self.assertIn(pointer, api.freed)
            api.emit()
            with self.assertRaisesRegex(TouchError, "没有事件数据"):
                touch.read(timeout=0)

    def test_registration_failure_closes_opened_session(self):
        api = FakeWinBio()
        api.fail_register = True
        with self.assertRaisesRegex(TouchError, "注册触摸监听"):
            self.connect(api)
        self.assertEqual(api.calls, ["open", "enum", "register", "close"])

    def test_device_selection_failure_frees_enumeration_and_closes_session(self):
        for devices in (("USB\\OTHER",), ("VID_3274&PID_8012", "VID_3274&PID_8012")):
            with self.subTest(devices=devices):
                api = FakeWinBio(devices)
                with self.assertRaises(TouchError):
                    self.connect(api)
                self.assertEqual(api.calls, ["open", "enum", "close"])
                self.assertEqual(len(api.freed), 1)

    def test_unregister_failure_still_closes_session_and_reports_error(self):
        api = FakeWinBio()
        touch = self.connect(api)
        api.fail_unregister = True
        with self.assertRaisesRegex(TouchError, "注销触摸监听"):
            touch.close()
        self.assertFalse(touch.is_connected)
        self.assertEqual(api.calls[-2:], ["unregister", "close"])
        self.assertNotIn(touch, _pending_cleanup)

    def test_failed_cleanup_retains_callback_and_can_be_retried(self):
        api = FakeWinBio()
        touch = self.connect(api)
        api.fail_unregister = api.fail_close = True
        try:
            with self.assertRaisesRegex(TouchError, "关闭指纹会话"):
                touch.close()
            self.assertIn(touch, _pending_cleanup)
            api.emit(_Unclaimed(FP_UNCLAIMED, 3, 0))
            self.assertIsNotNone(touch.read(timeout=0))
        finally:
            api.fail_unregister = api.fail_close = False
            touch.close()
        self.assertNotIn(touch, _pending_cleanup)

    def test_user_exception_still_releases_listener(self):
        api = FakeWinBio()
        with self.assertRaisesRegex(ValueError, "调用方错误"):
            with self.connect(api):
                raise ValueError("调用方错误")
        self.assertEqual(api.calls[-2:], ["unregister", "close"])

    def test_import_has_no_screen_dependencies_and_unsupported_os_fails_at_connect(self):
        result = subprocess.run([
            sys.executable, "-c",
            "import sys; import gem12_touch; "
            "assert not any(n.split('.')[0] in {'gem12_screen', 'serial', 'PIL'} for n in sys.modules)",
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with patch("gem12_touch.touch.sys.platform", "linux"):
            with self.assertRaisesRegex(TouchError, "仅支持 Windows"):
                FingerprintTouch.connect()

    def test_device_id_is_selected_after_session_initialization(self):
        api = FakeWinBio()
        original_open = api.WinBioOpenSession

        def changing_unit_open(*args):
            api.units[0].unit_id = 4
            return original_open(*args)

        api.WinBioOpenSession = changing_unit_open
        with self.connect(api) as touch:
            self.assertEqual(touch.unit_id, 4)
            api.emit(_Unclaimed(FP_UNCLAIMED, 4, 0))
            self.assertEqual(touch.read(timeout=0).unit_id, 4)

    def test_debug_logs_report_completed_callbacks_and_each_cleanup_step(self):
        api = FakeWinBio()
        with self.assertLogs("gem12_touch.touch", level="DEBUG") as logs:
            touch = self.connect(api)
            api.emit(_Unclaimed(FP_UNCLAIMED, 3, 0))
            touch.read(timeout=0)
            touch.read(timeout=0)
            touch.close()
        output = "\n".join(logs.output)
        self.assertIn("系统回调进入=1，结束=1", output)
        self.assertIn("注销触摸监听完成：耗时=", output)
        self.assertIn("关闭指纹会话完成：耗时=", output)

    def test_demo_reports_interrupt_before_native_cleanup_starts(self):
        from examples.listen_touch import main

        api = FakeWinBio()
        touch = self.connect(api)
        output = StringIO()
        native_close = api.WinBioCloseSession

        def checked_close(session):
            self.assertIn("正在关闭监听", output.getvalue())
            self.assertNotIn("监听已关闭", output.getvalue())
            return native_close(session)

        api.WinBioCloseSession = checked_close
        with patch("examples.listen_touch.FingerprintTouch.connect", return_value=touch):
            with patch.object(touch, "read", side_effect=KeyboardInterrupt):
                with redirect_stdout(output):
                    main([])
        self.assertIn("监听已关闭", output.getvalue())
        self.assertFalse(touch.is_connected)

    def test_demo_does_not_claim_cleanup_succeeded_if_close_is_interrupted(self):
        from examples.listen_touch import main

        api = FakeWinBio()
        touch = self.connect(api)
        output = StringIO()
        try:
            with patch("examples.listen_touch.FingerprintTouch.connect", return_value=touch):
                with patch.object(touch, "read", side_effect=KeyboardInterrupt):
                    with patch.object(api, "WinBioCloseSession", side_effect=KeyboardInterrupt):
                        with redirect_stdout(output):
                            main([])
            self.assertIn("监听清理状态未确认", output.getvalue())
            self.assertNotIn("监听已关闭", output.getvalue())
        finally:
            touch.close()


if __name__ == "__main__":
    unittest.main()
