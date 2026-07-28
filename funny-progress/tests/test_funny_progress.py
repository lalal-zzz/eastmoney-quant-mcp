"""funny-progress 单元测试(纯本地, 无网络)"""
import io
import time

from funny_progress import FunProgress, available_animations, funny_tqdm, register_animation
from funny_progress.animations import (
    get_frames,
    get_big_frames,
    _EMOJI,
    _ASCII,
    _EMOJI_BIG,
    _ASCII_BIG,
    _LINE_BIG,
)


def test_available_animations():
    anims = available_animations()
    assert "chicken" in anims
    assert "spinner" in anims
    assert set(_EMOJI) == set(_ASCII)
    assert set(_EMOJI_BIG) == set(_ASCII_BIG)
    # BIG 帧列表长度一致
    assert len(_EMOJI_BIG["chicken"]) == len(_ASCII_BIG["chicken"])


def test_frames_fallback_name():
    frames = get_frames("不存在的动画")
    assert frames == get_frames("chicken")
    big_frames = get_big_frames("不存在的动画")
    assert big_frames == get_big_frames("chicken")


def test_frames_encoding_selection():
    class FakeUTF8(io.StringIO):
        encoding = "utf-8"

    class FakeGBK(io.StringIO):
        encoding = "cp936"

    assert get_frames("chicken", FakeUTF8()) is _EMOJI["chicken"]
    assert get_frames("chicken", FakeGBK()) is _ASCII["chicken"]

    assert get_big_frames("chicken", FakeUTF8()) is _EMOJI_BIG["chicken"]
    assert get_big_frames("chicken", FakeGBK()) is _ASCII_BIG["chicken"]


def test_progress_lifecycle_enabled():
    buf = io.StringIO()
    with FunProgress(total=3, desc="测试", enabled=True, file=buf, big=False) as p:
        for _ in range(3):
            p.update()
    out = buf.getvalue()
    assert "测试" in out
    assert "100%" in out or "3/3" in out


def test_progress_animation_thread_writes_frames():
    buf = io.StringIO()
    p = FunProgress(total=10, desc="动画", enabled=True, file=buf, fps=20, big=False)
    time.sleep(0.3)
    p.close()
    out = buf.getvalue()
    assert any(f.strip()[:2] in out for f in _ASCII["chicken"] if f.strip())


def test_progress_big_mode_writes_multi_line():
    """BIG 模式: 验证多行帧内容出现在输出中"""
    buf = io.StringIO()
    with FunProgress(total=5, desc="跳舞", enabled=True, file=buf, fps=20, big=True) as p:
        time.sleep(0.3)  # 让动画线程画几帧
        for _ in range(5):
            time.sleep(0.01)
            p.update()
    out = buf.getvalue()
    # 至少出现某个 BIG 帧里的字符
    all_lines = set()
    for frame in _LINE_BIG["line_chicken"]:
        for line in frame:
            all_lines.add(line.strip())
    found = any(text in out for text in all_lines if text)
    assert found, "BIG 多行帧应出现在输出中"


def test_progress_disabled_is_silent():
    buf = io.StringIO()
    with FunProgress(total=5, desc="静默", enabled=False, file=buf, big=True) as p:
        p.update()
        p.update(2)
        p.set_description("不会显示")
    assert buf.getvalue() == ""


def test_progress_indeterminate_mode():
    buf = io.StringIO()
    with FunProgress(desc="不确定任务", enabled=True, file=buf, big=False) as p:
        p.update()
    assert "不确定任务" in buf.getvalue()


def test_iterable_and_custom_animation():
    buf = io.StringIO()
    register_animation("wave_test", ["/o/", "\\o\\"])
    assert "wave_test" in available_animations()
    assert list(funny_tqdm([1, 2, 3], desc="迭代", animation="wave_test", file=buf, enabled=True, big=False)) == [1, 2, 3]
    assert "3/3" in buf.getvalue() or "100%" in buf.getvalue()
