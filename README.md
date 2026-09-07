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
