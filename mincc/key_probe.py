"""按键字节探测器：诊断终端到底把 Shift+Enter / Alt+Enter / Option+Enter 发成什么。

当 mincc 的"Alt+Enter 换行"在你的终端不工作时，先跑这个脚本：

    uv run python -m mincc.key_probe

脚本启动时会请求支持的终端把 Alt/Option 按键可区分地上报，同时保留常规
Ctrl 编辑键。然后按你想测的键，脚本会打印出每次按键发出的原始字节序列。
Ctrl-C 退出。

判读结论:
- Shift+Enter 应该看到 ``\\n``、``\\x1b[13;2u`` 或 ``\\x1b[27;2;13~``
- Alt/Option+Enter 应该看到 ``\\x1b\\r``、``\\x1b\\n``、``\\x1b[13;3u`` 或
  ``\\x1b[27;3;13~``
- 单 Enter 应该看到 ``\\r``
- 如果 Shift+Enter 或 Option+Enter 只看到 ``\\r``，说明终端把它发成了普通 Enter，
  程序侧无法区分；需要在终端中开启对应的增强键盘协议或 Meta/Alt 发送方式：
  - macOS Terminal.app: Preferences -> Profiles -> Keyboard -> 勾 "Use Option as Meta key"
  - iTerm2: Preferences -> Profiles -> Keys -> Left/Right Option Key 改成 "Esc+"
  - iTerm2 不想全局改 Option 时：Profiles -> Keys -> Key Mappings 新增 Option+Enter，
    Action 选 "Send Hex Code"，内容填 ``0x1b 0x0d``（即 ESC + Enter）
"""

from __future__ import annotations

import os
import sys
import termios
import tty

from mincc.ui import TERMINAL_KEY_REPORTING_DISABLE, TERMINAL_KEY_REPORTING_ENABLE


def main() -> None:
    if not sys.stdin.isatty():
        print("[error] stdin 不是终端，无法探测按键", file=sys.stderr)
        sys.exit(1)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    print("按下任意键查看原始字节；Ctrl-C 退出。\n", flush=True)
    try:
        tty.setraw(fd)
        sys.stdout.write(TERMINAL_KEY_REPORTING_ENABLE)
        sys.stdout.flush()
        while True:
            data = os.read(fd, 32)
            if not data:
                continue
            if data == b"\x03":  # Ctrl-C
                break
            hex_repr = " ".join(f"{b:02x}" for b in data)
            ascii_repr = repr(data.decode("latin-1"))
            # 在 raw 模式下需要 \r\n 才能换行
            sys.stdout.write(f"bytes={ascii_repr:<24}  hex={hex_repr}\r\n")
            sys.stdout.flush()
    finally:
        sys.stdout.write(TERMINAL_KEY_REPORTING_DISABLE)
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print()


if __name__ == "__main__":
    main()
