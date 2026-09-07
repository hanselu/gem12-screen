# GEM12 Screen

使用 Python 通过 USB 串口控制 AOOSTAR GEM12 的 960×376 屏幕。项目只实现屏幕通信，不加载 WinRing0、LibreHardwareMonitor 或其他内核驱动，也不采集硬件数据。

## 使用

先退出官方 AOOSTAR-X 程序，避免它占用屏幕串口，然后运行：

```powershell
uv run python main.py
```

默认显示 `assets\backgrounds\background-01.jpg`。工程自带的 8 张 960×376 背景图位于 `assets\backgrounds`。显示其他图片：

```powershell
uv run python main.py --image .\picture.jpg
```

程序只会连接 USB VID/PID 为 `0416:90A1` 的串口。非 960×376 图片会先缩放，再转换为小端 RGB565 发送。

只发送开屏命令、不传图：

```powershell
uv run python main.py --open-only
```

完整的探查记录、协议格式和实现说明见 [屏幕协议与 Python 驱动说明](docs/屏幕协议与Python驱动说明.md)。
