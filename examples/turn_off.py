from gem12_screen import Screen


with Screen.connect(wake=False) as screen:
    screen.turn_off()
    print(f"屏幕 {screen.port} 已关闭")
