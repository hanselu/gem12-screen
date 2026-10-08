# AOOSTAR GEM12 屏幕探查与 Python 驱动说明

本文记录 2026-09-08 对 AOOSTAR GEM12 内置 960×376 屏幕及官方控制程序的静态分析、设备识别、协议恢复和 Python 真机验证结果。

2026-10-09 更新：当前设备已完成区域差分及 600 帧动态刷新验证，正式接口已加入差分缓存和强制整帧刷新。历史真机结果与当前实现说明分别记录，动态测试详情见[动态刷新验证记录](动态刷新验证记录.md)。

## 1. 结论

这块屏幕可以在 Windows 下通过普通 USB 串口直接控制，不需要加载 AOOSTAR-X 附带的 WinRing0、LibreHardwareMonitor、RyzenAdj 或 InpOut 内核组件，也不需要管理员权限。

已经完成并实际验证：

- 自动识别 `VID_0416&PID_90A1` 对应的屏幕串口；
- 以 1,500,000 波特率发送开屏命令；
- 发送关屏命令并验证设备响应；
- 将 960×376 RGB 图片转换成小端 RGB565；
- 按当前 AOOSTAR-X 协议发送完整画面；
- 连续显示两张不同的官方背景图；
- 屏幕返回 `0x41`，且两次画面均经人工确认符合预期。
- 在当前设备上通过局部差分更新、无变化帧保持画面及 600 帧连续动态验证，包含软件串口关闭后重新连接。

当前实现位于：

- `gem12_screen/screen.py`：对外的 `Screen` 高层控制接口；
- `gem12_screen/_protocol.py`：内部图像编码和串口协议实现；
- `gem12_screen/cli.py`：命令行入口；
- `gem12_screen/assets/example_images`：随包安装的 9 张自行绘制的 960×376 示例图片，编号为 `01.jpg`～`09.jpg`，采用项目的 0BSD 许可证；
- `examples/show_image.py`：只使用公共接口的调用示例；
- `examples/show_dashboard.py`：只使用公共接口的动态模拟仪表示例；
- `tests/test_protocol.py`：RGB565 和数据分块测试；
- `tests/test_screen.py`：公共 API、完整传图和异常关闭测试。

## 2. 分析范围与证据等级

### 2.1 已确认

- 设备的 USB VID/PID、串口号和 Windows 驱动；
- 当前安装程序所使用的串口参数、开屏命令和传图协议；
- RGB565 转换公式、字节序、数据块大小和偏移格式；
- 用户提供的可疑驱动 SHA1 与安装目录中 WinRing0 驱动一致；
- Python 实现可以在真机上完成开屏和两次画面切换。

### 2.2 根据静态代码推断

- `AOOSTAR-X.sys` 是 LibreHardwareMonitor 在运行时将内嵌 WinRing0 驱动提取到主程序同目录后形成的名称；
- 对应临时服务名很可能为 `R0AOOSTAR-X`，由 LibreHardwareMonitor 的服务命名逻辑生成。

驱动内容与重命名链路已有充分证据，但检查时 `AOOSTAR-X.sys` 已不存在，因此没有对该临时文件重新取样。

### 2.3 尚未验证

- 屏幕固件的完整命令集及错误码；
- 开屏响应以外是否还有稳定、可依赖的 ACK 格式；
- 更高刷新率动画、数小时持续运行及真实仪表数据采集；发送异常恢复使用模拟测试覆盖，不安排硬件拔插测试；
- 局部差分刷新在所有固件版本上的兼容性；
- Linux 版程序与当前 Windows 版是否完全使用相同协议。

## 3. 分析对象

### 3.1 参考目录

`reference` 目录包含两代官方程序及主题资源：

- `AOOSTAR-FAN_001/AOOSTAR-FAN.exe`
  - .NET Framework 4.7.2 WPF 程序；
  - 文件版本 `1.0.2.6`；
  - SHA256：`D3D7E06CA5860AC23A0AD917BD605B1A9287FB7A1FC11681CE51AE14A487097B`；
  - 随程序提供了 PDB，可以恢复较完整的类名和通信逻辑。
- `AOOSTAR-X V1.3.5/AOOSTAR-X-Setup V1.3.5.exe`
  - Advanced Installer 打包的安装程序；
  - 同目录还包含 Linux 程序和用户主题资源。
- `AOOSTAR-FAN_001/background`
  - 包含 8 张 960×376 JPEG 背景图；
  - 初期曾将这 8 张图片原样复制到包内，并命名为 `background-01.jpg` 至 `background-08.jpg`；现已全部替换为通过 `scripts/generate_example_images.py` 自行绘制的 9 张示例图片，编号为 `01.jpg` 至 `09.jpg`；
  - 当前运行时只读取包内的 `gem12_screen/assets/example_images`，不读取已被 Git 忽略的 `reference` 目录。

旧版程序中存在 `HidLibrary.dll` 和名为 `USBHIDCommunication` 的类，但其枚举目标是 `046D:C542`，而且没有进入实际屏幕发送链路。不能据此把屏幕误判为 HID 设备。

### 3.2 当前安装程序

安装目录：

```text
C:\Program Files (x86)\AOOSTAR-X
```

当前主程序：

```text
AOOSTAR-X.exe
SHA256 812750B01F6F1CDF954A32A017E0648B6FC0684A1F315F5ADF4A69993329C44E
```

它是 Python 3.12/PyInstaller one-dir 程序，附带 `pyserial`、Pillow、Flask、LibreHardwareMonitor、WinRing0、InpOut 和 RyzenAdj 等组件。串口传图代码可以与硬件监控代码明确分离。

卸载注册表显示的产品名是 `AOOSTAR-X V1.3.2`，而参考目录中的安装包标记为 1.3.5，主程序本身又没有可用的文件版本资源。因此本文把协议称为“当前实际安装版协议”，不单凭注册表断言其精确发行版本。

## 4. 驱动告警结论

用户报告火绒告警文件：

```text
C:\Program Files (x86)\AOOSTAR-X\AOOSTAR-X.sys
SHA1 D25340AE8E92A6D29F599FEF426A2BC1B5217299
```

该 SHA1 与安装目录中以下两份文件完全一致：

```text
C:\Program Files (x86)\AOOSTAR-X\WinRing0x64.sys
C:\Program Files (x86)\AOOSTAR-X\_internal\WinRing0x64.sys
```

共同指纹为：

```text
SHA1   D25340AE8E92A6D29F599FEF426A2BC1B5217299
SHA256 11BD2C9F9E2397C9A16E0990E4ED2CF0679498FE0FD418A3DFDAC60B5C160EE5
```

文件描述为 WinRing0，版本 `1.2.0.5`，带有 Noriyuki MIYAZAKI 的旧数字签名。静态代码显示 LibreHardwareMonitor 会把内嵌的 `WinRing0x64.gz` 解压到以当前主程序命名的 `.sys` 文件中，所以在 AOOSTAR-X 进程里得到 `AOOSTAR-X.sys`。

微软明确说明 `VulnerableDriver:WinNT/Winring0` 检测是有效的，并将 WinRing0 归类为已知漏洞驱动，对应 CVE-2020-14979。微软同时警告，将它加入安全软件排除项会降低系统防护能力：

- [Microsoft Defender Antivirus alert - VulnerableDriver:WinNT/Winring0](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/microsoft-defender-antivirus-alert-vulnerabledriver-winnt-winring0)
- [Microsoft recommended driver block rules](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/design/microsoft-recommended-driver-block-rules)

因此本项目不恢复、不放行也不加载该驱动。屏幕控制只依赖 Windows 自带 USB 串口驱动。

检查期间 `AOOSTAR-X.sys` 已不在安装目录中，也没有发现对应的 AOOSTAR/WinRing0 服务。现有证据无法判断它是被火绒隔离，还是由官方程序退出时自动清理。

系统中还发现了单独运行的 `inpoutx64` 内核驱动，但其 SHA1 为 `6AFC6B04CF73DD461E4A4956365F25C1F1162387`，与本次火绒告警指纹不同。本轮没有停止、卸载或修改该服务，也没有把它归因于某个确定的安装来源。

## 5. 屏幕设备与串口参数

Windows 设备枚举结果：

| 项目 | 值 |
|---|---|
| USB VID | `0x0416` |
| USB PID | `0x90A1` |
| 本次串口 | `COM3` |
| Windows 服务 | `usbser` |
| 波特率 | `1,500,000` |
| 数据位 | 8 |
| 校验位 | 无 |
| 停止位 | 1 |
| 读超时 | 1 秒 |
| 屏幕尺寸 | 960×376 |
| 像素格式 | RGB565，小端序 |

`COM3` 只是本机本次枚举结果，不应写死。Python 程序通过 VID/PID 寻找串口，并在用户显式传入 `--port` 时继续校验该端口是否属于目标设备，避免误写其他串口。

## 6. 当前已验证协议

所有十六进制数据均按实际线上字节顺序书写。

### 6.1 开屏

```text
AA 55 AA 55 0B 00 00 00
```

两次真机测试均收到：

```text
41
```

即 ASCII 字符 `A`。

### 6.2 关屏

```text
AA 55 AA 55 0A 00 00 00
```

真机发送结果为 8 字节完整写入，设备返回 `41`，随后由人工确认屏幕已经熄灭。

### 6.3 开始传图

```text
AA 55 AA 55 05 00 00 00 04 00 0F 2F 00 04 0B 00
```

后 8 字节来自官方程序中的 LVGL 图像头和区域参数。当前实现按已验证常量原样发送，不对其尚未完全确认的字段语义作进一步推断。

### 6.4 图像数据块

每个数据包的格式为：

```text
AA 55 AA 55 08 00 00 00
+ 4 字节小端序字节偏移
+ 最多 47 字节 RGB565 图像数据
```

偏移指向整幅 RGB565 字节流中的位置，不是像素序号。例如：

```text
第 1 块偏移：00 00 00 00
第 2 块偏移：2F 00 00 00  # 47
第 3 块偏移：5E 00 00 00  # 94
```

一幅完整画面的裸数据量为：

```text
960 × 376 × 2 = 721,920 字节
721,920 ÷ 47 = 15,360 个数据块
```

47 可以整除当前画面数据量，所以完整 960×376 画面没有不足 47 字节的尾块。

### 6.5 结束传图

```text
AA 55 AA 55 06 00 00 00
```

### 6.6 完整发送顺序

```text
打开 COM 口
  ↓
发送开屏命令 0x0B
  ↓
读取响应，正常为 0x41
  ↓
发送开始传图命令 0x05
  ↓
依次发送 15,360 个 0x08 数据块
  ↓
发送结束传图命令 0x06
  ↓
等待串口输出缓冲区发送完成
  ↓
关闭串口句柄，屏幕保持当前画面
```

包括包头和偏移字段在内，一次完整刷新发送约 906 KB 串口数据。

## 7. RGB565 编码

每个 RGB888 像素按官方程序使用的公式转换：

```python
pixel = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
```

然后将 16 位值按小端序写入：

```python
low_byte = pixel & 0xFF
high_byte = pixel >> 8
```

已通过单元测试验证的典型值：

| RGB888 | RGB565 数值 | 线上字节 |
|---|---:|---|
| 黑 `(0,0,0)` | `0x0000` | `00 00` |
| 白 `(255,255,255)` | `0xFFFF` | `FF FF` |
| 红 `(255,0,0)` | `0xF800` | `00 F8` |
| 绿 `(0,255,0)` | `0x07E0` | `E0 07` |
| 蓝 `(0,0,255)` | `0x001F` | `1F 00` |

图片不是 960×376 时，当前程序使用 Pillow 的 Lanczos 重采样缩放到目标尺寸。它不会自动裁剪，因此宽高比不同的图片会发生拉伸。

## 8. Python 封装与使用

### 8.1 环境

项目使用 Python 3.12，依赖：

- `pyserial`：串口枚举和发送；
- `Pillow`：读取、缩放及转换图片。

安装依赖：

```powershell
uv sync
```

### 8.2 在自己的程序中调用

上层程序只需导入 `Screen`，不需要接触串口号、波特率、命令字、RGB565 或分块规则：

```python
from gem12_screen import Screen

with Screen.connect() as screen:
    screen.show("picture.jpg")
```

`Screen.connect()` 会完成以下操作：

1. 按 VID/PID 自动寻找目标屏幕；
2. 打开串口；
3. 发送开屏命令；
4. 验证屏幕是否返回 ASCII `A`。

`screen.show()` 接受文件路径或 Pillow `Image` 对象，并返回本次发送的数据块数量。退出 `with` 后只关闭串口连接，不会关屏或清除画面。

同一连接中，首次显示发送整帧，后续显示比较新旧完整 RGB565 数据，按 47 字节块跳过未变化的数据；变化块的偏移仍指向原始完整画面，不重新编号。相同画面返回 `0`，仍发送开始和结束命令。

```python
with Screen.connect() as screen:
    screen.show(first_image)
    screen.show(next_image)
    screen.show(next_image, force_full=True)
```

调用方每次仍传入完整图片。绘制时从背景重新生成下一帧，避免旧文字或图形残留。差分优化减少串口发送量，当前 RGB565 编码仍处理整张图片。

每帧结束后只调用一次 `flush()`，随后读取当前可用的串口响应；这些响应不作为逐块或逐帧 ACK 判定。只有发送、flush 和响应读取成功后才提交新缓存。传输失败抛出 `ScreenError` 并使缓存失效，下次发送整帧，不自动重试。仅图片读取失败时保留之前的缓存。

`close()`、`wake()`、`turn_off()` 均使缓存失效；每个新连接独立维护缓存。若需要显式恢复画面，使用 `force_full=True`。

也可以显式指定端口，但仍会校验 VID/PID：

```python
with Screen.connect("COM3") as screen:
    screen.show("picture.jpg")
```

所有可预期的连接、响应和图片读取错误统一抛出 `ScreenError`：

```python
from gem12_screen import Screen, ScreenError

try:
    with Screen.connect() as screen:
        screen.show("picture.jpg")
except ScreenError as exc:
    print(f"屏幕控制失败：{exc}")
```

关闭屏幕时使用 `turn_off()`。传入 `wake=False` 可以只建立串口连接，避免在关屏前先发送开屏命令：

```python
with Screen.connect(wake=False) as screen:
    screen.turn_off()
```

`turn_off()` 使用已经过真机验证的 `AA 55 AA 55 0A 00 00 00` 命令，并要求设备返回 ASCII `A`。不要用 `close()` 代替关屏：`close()` 只释放串口句柄，屏幕会继续保持当前状态。

### 8.3 运行 Demo

`examples/show_image.py` 是最小调用示例：

```powershell
uv run python examples/show_image.py
```

Demo 使用 `Screen.connect()` 和 `screen.show()` 显示包内的 `02.jpg`，不直接调用任何内部协议函数。

### 8.4 使用命令行

先退出官方 AOOSTAR-X，避免它占用同一个串口，然后在项目目录运行：

```powershell
uv run gem12-screen
```

默认图片为：

```text
gem12_screen\assets\example_images\01.jpg
```

显示指定图片：

```powershell
uv run gem12-screen --image "D:\Pictures\screen.jpg"
```

显示工程自带的第 2 张示例图片：

```powershell
uv run gem12-screen --image ".\gem12_screen\assets\example_images\02.jpg"
```

只发送开屏命令：

```powershell
uv run gem12-screen --open-only
```

关闭屏幕：

```powershell
uv run gem12-screen --turn-off
```

显式指定串口：

```powershell
uv run gem12-screen --port COM3 --image ".\picture.jpg"
```

即使指定了 `COM3`，程序仍要求该端口的 VID/PID 是 `0416:90A1`。

## 9. 代码结构

包内文件和接口：

| 名称 | 作用 |
|---|---|
| `Screen.connect()` | 查找设备、打开串口并验证开屏响应 |
| `Screen.show(source, force_full=False)` | 首帧整帧，后续差分；可强制整帧，返回本次发送的块数 |
| `Screen.wake()` | 重新发送开屏命令并验证响应 |
| `Screen.turn_off()` | 发送关屏命令并验证响应 |
| `Screen.close()` | 关闭串口连接，不关闭屏幕 |
| `Screen.port` | 实际连接的串口名 |
| `Screen.is_connected` | 当前串口连接状态 |
| `_protocol.py` | 不对上层公开的协议常量、编码和分块实现 |

包的公开入口 `gem12_screen/__init__.py` 只导出 `Screen` 和 `ScreenError`。调用方不应依赖 `_protocol.py` 中以下划线开头的内部实现。

## 10. 旧版协议线索

旧版 .NET 程序使用相同的设备 VID/PID、波特率、960×376 RGB565 图像和 `AA 55 AA 55` 魔数，但命令编号与当前版本不同：

- 旧版传图开始命令使用 `0x01`；
- 旧版数据块使用 `0x07`；
- 旧版含 `0x02` 握手/结束流程，并在部分路径中逐块等待响应；
- 旧版还包含开屏 `0x0B`、关屏 `0x0A`、背光超时 `0x0C` 和模式 `0x0D` 等命令。

当前 Python 实现只采用已经在当前安装版和真机上成功验证的 `0x05 → 0x08 → 0x06` 传图流程，没有混用旧版分块协议。

## 11. 真机验证记录

### 第一次

- 图片：当时使用的官方背景图 `background-01.jpg`（现已从包内移除，非当前 `01.jpg`）；
- 分辨率：960×376；
- 串口：COM3；
- 开屏响应：`41`；
- 数据块：15,360；
- 人工结果：显示符合预期。

### 第二次

- 图片：当时使用的官方背景图 `background-02.jpg`（现已从包内移除，非当前 `02.jpg`）；
- 分辨率：960×376；
- 串口：COM3；
- 开屏响应：`41`；
- 数据块：15,360；
- 人工结果：已正确切换为指定图片。

### 关屏验证

- 测试前状态：屏幕正在显示画面；
- 命令：`AA 55 AA 55 0A 00 00 00`；
- 串口：COM3；
- 写入长度：8 字节；
- 设备响应：`41`；
- 人工结果：屏幕已熄灭。

离线测试同时验证了 RGB565 字节序和数据块偏移。当前测试命令：

```powershell
uv run python -m unittest discover -s tests -v
```

## 12. 使用注意事项

- 运行前应退出官方 AOOSTAR-X，两个程序不能同时独占同一串口。
- 不要为了屏幕功能恢复或放行 `AOOSTAR-X.sys`；传图不需要它。
- 不要把 COM3 写死到其他机器上，应继续依靠 VID/PID 枚举。
- 当前版本默认差分刷新。候选实现已在当前设备上完成目标每秒 2 次的 600 帧仪表验证，正式接口另完成 28 帧短时验证；候选测试出现过一次超出 0.5 秒的处理延迟，不能承诺严格实时刷新。数小时持续运行仍需在实际仪表布局下验证。
- 开屏或关屏没有返回 `0x41` 时，当前接口会抛出 `ScreenError` 并报告实际响应。传图响应只读取，不据此断言屏幕显示正确。
- 按用户要求，内置屏幕不安排硬件拔插测试；发送异常和缓存恢复用模拟测试覆盖。同一连接的控制与显示调用应顺序执行。
- Ghidra 适合继续分析附带的本机二进制组件，但恢复当前串口协议时，.NET/Python 静态分析和真机验证已经足够，没有必要反编译或加载存在风险的内核驱动。
