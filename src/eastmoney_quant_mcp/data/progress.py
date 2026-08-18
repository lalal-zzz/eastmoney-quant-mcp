"""
进度条挂载层: 使用 tqdm 标准进度条, 缺失时降级空实现。

所有输出写 stderr, 非 TTY 时 tqdm 自动静默, 不会污染 MCP stdio 协议通道(stdout)。
"""

import sys


class _NullProgress:
    """无操作进度条(兜底)"""

    def update(self, n=1):
        pass

    def set_description(self, desc):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_progress(total=None, desc=""):
    """
    创建 tqdm 进度条上下文管理器。

    total=None 为不确定模式(仅显示耗时和计数); tqdm 未安装时降级空实现。
    """
    try:
        from tqdm import tqdm
        return tqdm(total=total, desc=desc, file=sys.stderr)
    except ImportError:
        return _NullProgress()
"""
进度条挂载层: 优先使用 funny-tqdm(动画进度条), 缺失时降级纯 tqdm, 再缺失则空实现。

big=True 时启用多行跳舞动画(坤坤打篮球), 否则只用单行后缀动画。
所有实现只写 stderr 且在非 TTY 时静默, 不会污染 MCP stdio 协议通道(stdout)。
"""

import sys


class _NullProgress:
    """无操作进度条(兜底)"""

    def update(self, n=1):
        pass

    def set_description(self, desc):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_progress(total=None, desc="", animation="chicken", big=True):
    """
    创建进度条上下文管理器。

    total=None 为不确定模式(仅动画+耗时); funny-tqdm 未安装时降级纯 tqdm。
    big=True 时(默认)使用多行跳舞动画, 否则单行动画。
    """
    try:
        from funny_tqdm import FunProgress
        return FunProgress(total=total, desc=desc, animation=animation, big=big)
    except ImportError:
        pass
    try:
        from tqdm import tqdm
        return tqdm(total=total, desc=desc, file=sys.stderr)
    except ImportError:
        return _NullProgress()
