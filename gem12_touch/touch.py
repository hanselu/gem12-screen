from __future__ import annotations

import ctypes as c
import logging
from dataclasses import dataclass
from queue import Empty, SimpleQueue
import sys
from time import monotonic
from types import TracebackType


DWORD = c.c_uint32
HRESULT = c.c_int32
CALLBACK = getattr(c, "WINFUNCTYPE", c.CFUNCTYPE)(None, c.c_void_p, HRESULT, c.c_void_p)
TARGET_DEVICE = "VID_3274&PID_8012"
FP_UNCLAIMED = 1
EVENT_ERROR = 0xFFFFFFFF
logger = logging.getLogger(__name__)


class _Version(c.Structure):
    _fields_ = [("major", DWORD), ("minor", DWORD)]


class _UnitSchema(c.Structure):
    _fields_ = [
        ("unit_id", DWORD), ("pool", DWORD), ("factor", DWORD),
        ("subtype", DWORD), ("capabilities", DWORD),
        ("device_instance", c.c_wchar * 256), ("description", c.c_wchar * 256),
        ("manufacturer", c.c_wchar * 256), ("model", c.c_wchar * 256),
        ("serial_number", c.c_wchar * 256), ("firmware", _Version),
    ]


class _Unclaimed(c.Structure):
    _fields_ = [("type", DWORD), ("unit_id", DWORD), ("reject_detail", DWORD)]


class _ErrorEvent(c.Structure):
    _fields_ = [("type", DWORD), ("error_code", HRESULT)]


class TouchError(RuntimeError):
    """指纹触摸监听连接、通知或清理失败。"""


@dataclass(frozen=True)
class TouchEvent:
    """目标传感器的采样通知；timestamp 为收到通知时的单调时钟秒数。"""

    unit_id: int
    timestamp: float
    reject_detail: int


def _check(hr: int, action: str) -> None:
    if hr < 0:
        raise TouchError(f"{action}失败：HRESULT 0x{hr & 0xFFFFFFFF:08X}")


def _load_api():
    if sys.platform != "win32":
        raise TouchError("指纹触摸监听仅支持 Windows")
    try:
        api = c.WinDLL("C:/Windows/System32/winbio.dll")
    except OSError as exc:
        raise TouchError(f"无法加载 Windows 生物识别接口：{exc}") from exc
    api.WinBioEnumBiometricUnits.argtypes = [DWORD, c.POINTER(c.POINTER(_UnitSchema)), c.POINTER(c.c_size_t)]
    api.WinBioOpenSession.argtypes = [DWORD, DWORD, DWORD, c.POINTER(DWORD), c.c_size_t, c.c_void_p, c.POINTER(DWORD)]
    api.WinBioRegisterEventMonitor.argtypes = [DWORD, DWORD, CALLBACK, c.c_void_p]
    api.WinBioUnregisterEventMonitor.argtypes = [DWORD]
    api.WinBioCloseSession.argtypes = [DWORD]
    api.WinBioFree.argtypes = [c.c_void_p]
    for name in ("WinBioEnumBiometricUnits", "WinBioOpenSession", "WinBioRegisterEventMonitor",
                 "WinBioUnregisterEventMonitor", "WinBioCloseSession"):
        getattr(api, name).restype = HRESULT
    api.WinBioFree.restype = None
    return api


def _find_unit(api) -> int:
    units = c.POINTER(_UnitSchema)()
    count = c.c_size_t()
    try:
        _check(api.WinBioEnumBiometricUnits(8, c.byref(units), c.byref(count)), "枚举指纹设备")
        matches = [units[i].unit_id for i in range(count.value)
                   if TARGET_DEVICE in units[i].device_instance.upper()]
    finally:
        if units:
            api.WinBioFree(units)
    if not matches:
        raise TouchError(f"未找到指纹设备 {TARGET_DEVICE}")
    if len(matches) != 1:
        raise TouchError("检测到多个目标指纹设备，无法确定监听对象")
    return matches[0]


# 清理失败时保留回调，避免仍在运行的原生监听调用已释放的 ctypes 函数。
_pending_cleanup: set[FingerprintTouch] = set()


class FingerprintTouch:
    """独立的 Windows 指纹触摸通知队列，不识别身份或操作屏幕。"""

    def __init__(self, unit_id: int, api) -> None:
        self.unit_id = unit_id
        self._api = api
        self._session = DWORD()
        self._registered = False
        self._events: SimpleQueue[TouchEvent | TouchError] = SimpleQueue()
        self._callbacks_started = 0
        self._callbacks_finished = 0
        self._last_ignored_unit_id: int | None = None
        self._callback = CALLBACK(self._on_event)

    @classmethod
    def connect(cls) -> FingerprintTouch:
        """寻找 Microarray 3274:8012 并注册不识别身份的通知。"""
        api = _load_api()
        listener = cls(0, api)
        try:
            _check(api.WinBioOpenSession(8, 1, 0, None, 0, c.c_void_p(1),
                                        c.byref(listener._session)), "打开指纹会话")
            # 打开会话可能初始化或重建设备，应在此之后确定当前编号。
            listener.unit_id = _find_unit(api)
            logger.debug("打开会话后选定目标指纹设备：Unit ID=%d", listener.unit_id)
            _check(api.WinBioRegisterEventMonitor(listener._session, FP_UNCLAIMED,
                                                  listener._callback, None), "注册触摸监听")
            listener._registered = True
        except BaseException as exc:
            try:
                listener.close()
            except TouchError as cleanup_error:
                exc.add_note(str(cleanup_error))
            raise
        return listener

    @property
    def is_connected(self) -> bool:
        return bool(self._session.value) and self._registered

    def __enter__(self) -> FingerprintTouch:
        self._require_connection()
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        self.close()

    def read(self, timeout: float | None = None) -> TouchEvent | None:
        """取出一条通知；超时返回 None，timeout=0 不等待，None 持续等待。"""
        self._require_connection()
        try:
            event = self._events.get(timeout=timeout)
        except Empty:
            logger.debug("等待超时；系统回调进入=%d，结束=%d；目标设备=%d，最近忽略设备=%s",
                         self._callbacks_started, self._callbacks_finished,
                         self.unit_id, self._last_ignored_unit_id)
            return None
        if isinstance(event, TouchError):
            logger.debug("读取通知错误：%s", event)
            raise event
        logger.debug("读取通知：设备=%d，RejectDetail=%d；系统回调进入=%d，结束=%d",
                     event.unit_id, event.reject_detail,
                     self._callbacks_started, self._callbacks_finished)
        return event

    def close(self) -> None:
        """注销通知并关闭会话；不停止共享的 Windows 生物识别服务。"""
        if not self._session.value:
            return
        errors = []
        if self._registered:
            logger.debug("开始注销触摸监听")
            started = monotonic()
            hr = self._api.WinBioUnregisterEventMonitor(self._session)
            logger.debug("注销触摸监听完成：耗时=%.3f 秒，HRESULT=0x%08X",
                         monotonic() - started, hr & 0xFFFFFFFF)
            if hr < 0:
                errors.append(f"注销触摸监听失败：HRESULT 0x{hr & 0xFFFFFFFF:08X}")
            else:
                self._registered = False
        logger.debug("开始关闭指纹会话")
        started = monotonic()
        hr = self._api.WinBioCloseSession(self._session)
        logger.debug("关闭指纹会话完成：耗时=%.3f 秒，HRESULT=0x%08X",
                     monotonic() - started, hr & 0xFFFFFFFF)
        if hr < 0:
            errors.append(f"关闭指纹会话失败：HRESULT 0x{hr & 0xFFFFFFFF:08X}")
            _pending_cleanup.add(self)
        else:
            self._session.value = 0
            self._registered = False
            _pending_cleanup.discard(self)
        if errors:
            raise TouchError("；".join(errors))

    def _require_connection(self) -> None:
        if not self.is_connected:
            raise TouchError("指纹触摸监听已经关闭")

    def _on_event(self, context, status: int, pointer) -> None:
        self._callbacks_started += 1
        try:
            _check(status, "触摸通知")
            if not pointer:
                raise TouchError("触摸通知没有事件数据")
            event_type = c.cast(pointer, c.POINTER(DWORD)).contents.value
            if event_type == FP_UNCLAIMED:
                event = c.cast(pointer, c.POINTER(_Unclaimed)).contents
                if event.unit_id == self.unit_id:
                    self._events.put(TouchEvent(event.unit_id, monotonic(), event.reject_detail))
                else:
                    self._last_ignored_unit_id = event.unit_id
            elif event_type == EVENT_ERROR:
                event = c.cast(pointer, c.POINTER(_ErrorEvent)).contents
                raise TouchError(f"生物识别服务事件错误：HRESULT 0x{event.error_code & 0xFFFFFFFF:08X}")
        except Exception as exc:
            error = exc if isinstance(exc, TouchError) else TouchError(f"解析触摸通知失败：{exc}")
            self._events.put(error)
        finally:
            try:
                if pointer:
                    self._api.WinBioFree(pointer)
            finally:
                self._callbacks_finished += 1
