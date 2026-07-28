"""
funny-progress: tqdm 进度条 + 沙雕动画(坤坤打篮球等), 让漫长的等待不那么无聊。
"""

from .core import FunProgress
from .animations import available_animations, register_animation


def funny_tqdm(iterable=None, **kwargs):
    """tqdm 风格入口：``for x in funny_tqdm(items, animation='rocket')``。"""
    if iterable is None:
        return FunProgress(**kwargs)
    return FunProgress.iterable(iterable, **kwargs)

DEFAULT_ANIMATION = "chicken"

__version__ = "0.2.0"
__all__ = ["FunProgress", "funny_tqdm", "available_animations", "register_animation", "DEFAULT_ANIMATION"]
