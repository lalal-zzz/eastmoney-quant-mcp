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
