"""
FunProgress: tqdm 进度条 + 沙雕动画, 让漫长的等待不那么无聊。

动画以独立线程渲染:
- 普通模式: 刷新在进度条后缀位, 单行动画
- BIG 模式: 在进度条上方画多行动画(坤坤跳舞打篮球), ANSI 转义序列原位刷帧
所有输出只写 stderr, 不污染 stdout(对 stdio 类协议如 MCP 安全);
非 TTY 环境(重定向/日志管道)自动完全静默。
"""

import sys
import threading

from tqdm import tqdm

from .animations import (
    get_frames,
    get_big_frames,
    available_animations,
    _DEFAULT_ANIMATION,
)

__all__ = ["FunProgress", "available_animations", "DEFAULT_ANIMATION"]
DEFAULT_ANIMATION = _DEFAULT_ANIMATION


class FunProgress:
    """
    带动画的进度条。

    参数:
        total:     总步数; None 为不确定模式(只显示动画+耗时)
        desc:      进度条前缀描述
        animation: 动画名(见 available_animations()), 默认 chicken
        big:       多行跳舞模式(True=4行坤坤跳舞, 默认 True)
        fps:       动画帧率, 默认 12
        file:      输出流, 默认 sys.stderr
        enabled:   None=自动(仅 TTY 时启用); True=强制; False=静默
    """

    def __init__(self, total=None, desc="", animation=None, big=True,
                 fps=12, file=None, enabled=None, sync_speed=True):
        self._file = file if file is not None else sys.stderr
        if enabled is None:
            enabled = bool(getattr(self._file, "isatty", lambda: False)())
        self._enabled = bool(enabled)

        self._big = big and self._enabled
        # 默认展示纯线稿；保留 chicken 名称的旧动画 API。
        visual_animation = "line_chicken" if animation in (None, "chicken") else animation
        if self._big:
            self._frames = get_big_frames(visual_animation, self._file)
            # 给进度条 1 行留白防止帧被切
            bar_format = "{desc}  {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}  {elapsed}<{remaining}  {rate_fmt}"
            if total is None:
                bar_format = "{desc}  耗时 {elapsed}  {postfix}"
        else:
            self._frames = get_frames(animation, self._file)
            bar_format = None if total is not None else "{desc}  耗时 {elapsed}  {postfix}"

        self._frame_idx = 0
        self._sync_speed = sync_speed
        self._stop = threading.Event()
        self._thread = None
        self._prev_big_h = 0  # 上一帧行数(用于擦除)

        self._bar = tqdm(
            total=total,
            desc=desc,
            file=self._file,
            disable=not self._enabled,
            bar_format=bar_format,
            dynamic_ncols=True,
            leave=True,
        )

        if self._enabled:
            self._thread = threading.Thread(target=self._animate, args=(max(fps, 1),), daemon=True)
            self._thread.start()

    @classmethod
    def iterable(cls, iterable, **kwargs):
        """像 ``tqdm(iterable)`` 一样包装可迭代对象。"""
        items = iterable
        total = kwargs.pop("total", None)
        if total is None:
            try:
                total = len(iterable)
            except TypeError:
                pass
        progress = cls(total=total, **kwargs)
        try:
            for item in items:
                yield item
                progress.update()
        finally:
            progress.close()

    # ── 多行动画(进度条上方跳舞) ──

    def _render_big(self, frame_lines):
        h = len(frame_lines)

        # 擦除上一帧(光标上移 + 清行)
        if self._prev_big_h:
            erase = "".join(f"\033[1A\033[2K" for _ in range(self._prev_big_h))
            self._file.write(erase)

        # 写入新帧(一次性多行写, tqdm.write 确保写在进度条上方)
        tqdm.write("\n".join(frame_lines), file=self._file)

        self._prev_big_h = h
        # 刷新进度条(让耗时/百分比保持更新)
        self._bar.refresh()

    def _animate(self, fps):
        while not self._stop.wait(self._animation_interval(fps)):
            idx = self._frame_idx
            self._frame_idx += 1
            try:
                frame = self._frames[idx % len(self._frames)]
                if self._big:
                    self._render_big(frame)
                else:
                    self._bar.set_postfix_str(frame, refresh=True)
            except Exception:
                break

    def _animation_interval(self, fps):
        """根据 tqdm 的实时 rate 调整节奏；未知速率时使用用户设定 fps。"""
        if not self._sync_speed:
            return 1.0 / fps
        rate = self._bar.format_dict.get("rate") or 0.0
        if rate <= 0:
            return 1.0 / fps
        return max(0.035, min(0.45, 1.0 / (fps * max(0.35, min(3.0, rate)))))

    def update(self, n=1):
        """推进 n 步"""
        if self._enabled:
            self._bar.update(n)

    def set_description(self, desc):
        if self._enabled:
            self._bar.set_description(desc)

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._enabled:
            if self._big:
                # 擦除多行动画区域
                if self._prev_big_h:
                    erase = "".join(f"\033[1A\033[2K" for _ in range(self._prev_big_h))
                    try:
                        self._file.write(erase)
                        self._file.flush()
                    except Exception:
                        pass
            else:
                try:
                    self._bar.set_postfix_str("", refresh=False)
                except Exception:
                    pass
        self._bar.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
