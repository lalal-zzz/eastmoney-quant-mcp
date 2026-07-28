"""
动画帧库: 每组动画为一行/多行帧, 循环播放于 tqdm 进度条上方或后缀位。

- emoji 帧: UTF-8 终端(现代 Windows Terminal / macOS / Linux)
- ascii 帧: 重定向管道或 GBK 等无法输出 emoji 的环境自动降级
- BIG 帧: 多行动画, 在进度条上方跳舞(坤坤打篮球)
- 普通帧: 单行动画, 放在进度条后缀位
"""

_DEFAULT_ANIMATION = "chicken"

# 用户可注册自己的动画，避免为了加一个图案修改包源码。
_CUSTOM = {}


def register_animation(name, frames, big_frames=None):
    """注册动画；``frames`` 是单行字符串序列，``big_frames`` 是多行帧序列。"""
    if not name or not frames:
        raise ValueError("name 和 frames 不能为空")
    _CUSTOM[str(name)] = (list(frames), list(big_frames or [[str(frame)] for frame in frames]))

# ════════════════════════════════════════════
# 单行帧(进度条后缀位)
# ════════════════════════════════════════════

_EMOJI = {
    "chicken": [
        "🐔🏀   ", "🐔 🏀  ", "🐔  🏀 ", "🐔   🏀",
        "🐔  🏀 ", "🐔 🏀  ",
        "🐔🏀💃 ~",
        "🐔🎤  鸡你太美~",
    ],
    "runner": [
        "🏃→    ", " 🏃→   ", "  🏃→  ", "   🏃→ ",
        "    🏃→", "   🏃→ ", "  🏃→  ", " 🏃→   ",
    ],
    "rocket": [
        "🚀·    ", "🚀 ·   ", "🚀  ·  ", "🚀   · ",
        "🚀    ·", "🚀   · ", "🚀  ·  ", "🚀 ·   ",
    ],
    "spinner": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
}

_ASCII = {
    "chicken": [
        "<('')o    ", "<('') o   ", "<('')  o  ", "<('')   o ",
        "<('')  o  ", "<('') o   ",
        "<('')o~*  ",
        "ji ni tai mei ~",
    ],
    "runner": [
        "=>     ", " =>    ", "  =>   ", "   =>  ",
        "    => ", "     =>", "   =>  ", " =>    ",
    ],
    "rocket": [
        "^·    ", "^ ·   ", "^  ·  ", "^   · ",
        "^    ·", "^   · ", "^  ·  ", "^ ·   ",
    ],
    "spinner": ["|", "/", "-", "\\"],
}

# ════════════════════════════════════════════
# 多行 BIG 帧(进度条上方跳舞)
# ════════════════════════════════════════════

_EMOJI_BIG = {
    "chicken": [
        # F0  原地运球
        [
            "        🏀        ",
            "      <(o_o)>      ",
            "       /|\\\\       ",
            "       / \\\\        ",
        ],
        # F1  左运
        [
            "      🏀          ",
            "    <(o_o)        ",
            "      /|\\\\        ",
            "      / \\\\         ",
        ],
        # F2  右运
        [
            "          🏀      ",
            "        (o_o)>    ",
            "        /|\\\\      ",
            "        / \\\\       ",
        ],
        # F3  转球
        [
            "      ~~🏀~~      ",
            "     <(o_o)~      ",
            "       /|\\\\ ~     ",
            "      ~/ \\\\       ",
        ],
        # F4  铁山靠(左肩)
        [
            "   🏀              ",
            " (o_o)>            ",
            "  /|               ",
            "  / \\\\             ",
        ],
        # F5  铁山靠(右肩)
        [
            "              🏀   ",
            "            <(o_o)",
            "               /| \\\\",
            "               / \\\\ ",
        ],
        # F6  顶胯(经典动作)
        [
            "      🏀          ",
            "    ╭(o_o)╮      ",
            "     ╯ | ╰       ",
            "       / \\\\       ",
        ],
        # F7  唱跳收尾
        [
            "   🐔 鸡你太美 ~  🐔",
            "  (=≧▽≦=)        ",
            "    \\\\|/||\\\\|/    ",
            "     ╱ ╲          ",
        ],
    ],
}

_ASCII_BIG = {
    "chicken": [
        # F0
        [
            "        o        ",
            "      <(o_o)>     ",
            "       /|\\       ",
            "       / \\        ",
        ],
        # F1
        [
            "      o          ",
            "    <(o_o)       ",
            "      /|\\        ",
            "      / \\         ",
        ],
        # F2
        [
            "          o      ",
            "        (o_o)>   ",
            "        /|\\      ",
            "        / \\       ",
        ],
        # F3
        [
            "      ~ o ~      ",
            "     <(o_o)~     ",
            "       /|\\ ~     ",
            "      ~/ \\       ",
        ],
        # F4
        [
            "   o             ",
            " (o_o)>          ",
            "  /|             ",
            "  / \\             ",
        ],
        # F5
        [
            "              o   ",
            "            <(o_o)",
            "               /|\\",
            "               / \\ ",
        ],
        # F6
        [
            "      o          ",
            "    <(o_o)>      ",
            "     \\|/         ",
            "       / \\        ",
        ],
        # F7
        [
            "  ji ni tai mei ~",
            "   <(^_^)>        ",
            "    \\|/||\\|/     ",
            "     / \\          ",
        ],
    ],
}

# 纯线稿动画：不依赖 emoji，适合 Windows 控制台、日志和窄终端。
_LINE_BIG = {
    "line_chicken": [
        ["       .---.       ", "      / o o \\\\      ", "     |   ^   |      ", "      \\\\_=_/  o      ", "       /|\\\\          ", "       / \\\\          "],
        ["                 o ", "       .---.       / ", "      / o o \\\\     /  ", "     |   ^   |    o   ", "      \\\\_=_/    \\\\     ", "       /|\\\\     \\\\    "],
        ["           o       ", "          /         ", "       .---.        ", "      / o o \\\\       ", "     |   ^   |       ", "      \\\\_=_/          "],
        ["       o           ", "      /            ", "       .---.        ", "      / ^ ^ \\\\       ", "     |  ~~~  |       ", "      \\\\_=_/          "],
        ["          .---.    ", "         / o o \\\\    ", "        |   ^   |    ", "     o   \\\\_=_/      ", "    /    /|\\\\        ", "        / \\\\         "],
    ],
    "squirrel": [
        ["      /\\_/\\       ", "     ( o.o )       ", "      > ^ <   __   ", "     /|   |\\ /  \\\\ ", "    (_|___|_)      ", "      /   \\\\       "],
        ["       /\\_/\\      ", "      ( o.o )      ", "       > ^ <   __  ", "      /|   |\\ /  \\\\ ", "     (_|___|_)     ", "       /\\         "],
        ["        /\\_/\\     ", "       ( ^.^ )     ", "        > ^ <  __  ", "       /|   |\\/  ", "      (_|___|_)    ", "        /  \\\\      "],
        ["      /\\_/\\       ", "     ( -.- )       ", "      > ^ <  __    ", "     /|   |\\/  \\\\ ", "    (_|___|_)      ", "      /   \\\\       "],
    ],
}


def available_animations() -> list:
    """全部可用动画名"""
    return sorted(set(_EMOJI) | set(_LINE_BIG) | set(_CUSTOM))


def get_frames(name=None, file=None) -> list:
    """单行帧(用于进度条后缀位)"""
    enc = (getattr(file, "encoding", None) or "").lower()
    if name in _CUSTOM:
        return _CUSTOM[name][0]
    table = _EMOJI if "utf" in enc else _ASCII
    return table.get(name) or table[_DEFAULT_ANIMATION]


def get_big_frames(name=None, file=None) -> list:
    """多行 BIG 帧(用于进度条上方跳舞)"""
    enc = (getattr(file, "encoding", None) or "").lower()
    if name in _CUSTOM:
        return _CUSTOM[name][1]
    if name in _LINE_BIG:
        return _LINE_BIG[name]
    table = _EMOJI_BIG if "utf" in enc else _ASCII_BIG
    return table.get(name) or table[_DEFAULT_ANIMATION]
