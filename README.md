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
