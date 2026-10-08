# GEM12 Screen

使用 Python 通过 USB 串口控制 AOOSTAR GEM12 的 960×376 屏幕。屏控细节已经封装成可安装的 Python 包，不加载 WinRing0、LibreHardwareMonitor 或其他内核驱动，也不采集硬件数据。

## 安装

```powershell
uv sync
```

## Python 调用

```python
from gem12_screen import Screen

with Screen.connect() as screen:
    screen.show("picture.jpg")
```

`Screen.connect()` 会自动查找 USB VID/PID 为 `0416:90A1` 的串口、发送开屏命令并验证设备响应。`show()` 接受图片路径或 Pillow `Image` 对象，内部完成缩放、RGB565 编码和分块传输。

关闭屏幕：

```python
with Screen.connect(wake=False) as screen:
    screen.turn_off()
```

`turn_off()` 会让屏幕熄灭；`close()` 只关闭串口连接，不改变屏幕状态。

## 动态仪表与差分刷新

在同一个连接中连续调用 `show()`：首次发送整帧，后续只发送 RGB565 数据中变化的 47 字节块。画面不变时返回 `0`，仍发送帧开始、结束命令并读取当前可用的响应。

```python
from PIL import Image, ImageDraw

from gem12_screen import Screen

first_image = Image.new("RGB", (960, 376), "black")
next_image = first_image.copy()
ImageDraw.Draw(next_image).text((20, 20), "CPU: 9%", fill="white")

with Screen.connect() as screen:
    screen.show(first_image)   # Pillow Image，首次整帧
    screen.show(next_image)    # 仍传入完整图片，内部计算差分
    screen.show(next_image, force_full=True)  # 强制整帧刷新
```

绘制下一帧时，应从背景重新生成完整图片，确保缩短的文字、回落的进度条及移动图形的旧位置被清除。同一连接的调用应顺序执行。

缓存属于当前连接。新连接、`wake()`、`turn_off()` 或发送／响应读取失败后，下一次 `show()` 都发送整帧。图片读取失败不会影响已有缓存，因为此时尚未向屏幕发送数据。失败会抛出 `ScreenError`，不会自动重试。

模拟仪表 Demo：

```powershell
uv run python examples/show_dashboard.py
```

Demo 约以每秒 2 次更新 CPU 文字、内存文字和进度条，运行 28 帧后结束，不采集真实硬件数据。关闭串口后屏幕保留最后一帧。

差分刷新已通过当前设备的单次区域更新及 600 帧连续动态验证，均有目视确认。它仍编码完整图像，不能保证严格固定的刷新周期；数小时持续运行尚未验证。详见[差分刷新验证记录](docs/差分刷新验证记录.md)和[动态刷新验证记录](docs/动态刷新验证记录.md)。硬件拔插不作为本项目的测试或验收条件。

## Demo

先退出官方 AOOSTAR-X，避免它占用屏幕串口，然后运行：

```powershell
uv run python examples/show_image.py
```

Demo 显示包内的 `gem12_screen/assets/backgrounds/background-02.jpg`。

## 命令行

显示默认背景图：

```powershell
uv run gem12-screen
```

显示指定图片：

```powershell
uv run gem12-screen --image .\picture.jpg
```

只发送开屏命令：

```powershell
uv run gem12-screen --open-only
```

关闭屏幕：

```powershell
uv run gem12-screen --turn-off
```

完整的探查记录、协议格式和实现说明见 [屏幕协议与 Python 驱动说明](docs/屏幕协议与Python驱动说明.md)。

## 独立的指纹轻触监听（Windows）

项目同时提供 `gem12_touch`，使用机器现有的 Microarray `3274:8012` 驱动监听不识别身份的指纹通知。它与 `gem12_screen` 独立：不导入屏控、串口或 Pillow，也不连接屏幕。安装包包含两个可分别使用的 Python 包。

```python
from gem12_touch import FingerprintTouch

with FingerprintTouch.connect() as touch:
    while True:
        event = touch.read(timeout=0.5)
        if event is not None and event.reject_detail == 0:
            print("收到轻触通知", event.unit_id)
```

`read()` 按接收顺序取出通知，超时返回 `None`；`timeout=0` 不等待，默认 `None` 持续等待。事件包含 `unit_id`、收到通知时的单调时钟 `timestamp` 和采样拒绝信息 `reject_detail`；只有 `reject_detail == 0` 时才按成功输入处理。连接或监听失败抛出 `TouchError`。`close()` 可重复调用，上下文退出时自动注销监听并关闭会话。

独立示例只打印通知，按 Ctrl+C 退出：

```powershell
uv run python examples/listen_touch.py
```

若出现触摸后不再通知或退出较慢，用诊断模式记录系统回调计数和清理步骤耗时：

```powershell
uv run python examples/listen_touch.py --debug
```

按 Ctrl+C 后会先显示关闭提示，再等待 Windows 注销监听和释放会话。同步清理可能等待系统返回；已有异常日志确认 `WinBioCloseSession` 耗时约 10 秒，不应视为固定正常耗时。通知停止的根因仍待排查，详见[通知中断与退出诊断](docs/轻触通知中断与退出诊断.md)。程序不会根据无通知时长自动重连，因为无法区分正常空闲与监听故障。

Windows 重建设备后 Unit ID 可能变化。连接时会先打开会话，再枚举当前目标编号；诊断输出也会记录最近因编号不匹配而忽略的设备。此修正避免在会话初始化前固定旧编号，不等于已经修复所有通知中断。

屏幕显示、页面切换等业务由调用方处理；不要放入系统回调。`read()` 和 `close()` 应由同一调用线程顺序使用，系统回调仅负责把通知放入队列。

这里的“轻触”是本项目的使用方式，不是接口对接触时长的分类；长按也可能产生相同通知。没有长按判断或自动去重，也不保证每次接触必定产生一个事件。正式接口的测试及真机结果见[独立轻触接口验收](docs/独立轻触接口验证记录.md)，前期探索见[触摸事件记录](docs/指纹触摸事件验证记录.md)及[长按对照记录](docs/指纹长按验证记录.md)。

Windows 可能自动启动 `WbioSrvc`，关闭监听不会停止这个共享服务，也不需要以管理员权限运行示例。此功能不录入或识别指纹、不读取模板、不替换驱动。与 Windows Hello 的同时使用及长期运行尚未验证；应用在系统睡眠前应关闭监听，唤醒后重新连接，参见[微软事件监听说明](https://learn.microsoft.com/en-us/windows/win32/api/winbio/nf-winbio-winbioregistereventmonitor)。
