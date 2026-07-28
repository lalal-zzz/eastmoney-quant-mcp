# funny-progress

tqdm 进度条 + 沙雕动画（**坤坤打篮球** / 跑步 / 火箭 / spinner），让漫长的等待不那么无聊。

- 动画播放在进度条后缀位，自带耗时 / ETA（tqdm 原生）
- 只写 **stderr**，不污染 stdout（对 stdio 协议如 MCP 安全）
- 非 TTY 环境（重定向 / 日志管道）自动完全静默
- 终端不支持 UTF-8 时自动从 emoji 降级为 ASCII 帧

## 安装

```bash
pip install funny-progress
```

## 用法

```python
from funny_progress import FunProgress

# 确定总量: 进度条 + 百分比 + 耗时/ETA + 动画
with FunProgress(total=len(items), desc="下载板块K线") as p:
    for item in items:
        do_something(item)
        p.update()

# 不确定总量: 只显示 描述 + 耗时 + 动画
with FunProgress(desc="下载全市场行情..."):
    fetch_everything()

# 换动画
with FunProgress(total=100, desc="跑步前进", animation="runner") as p:
    ...

# tqdm 风格的可迭代入口
from funny_progress import funny_tqdm
for item in funny_tqdm(items, desc="处理数据", animation="rocket"):
    do_something(item)

# 注册自定义动画（单行帧；big_frames 可选）
from funny_progress import register_animation
register_animation("wave", ["/o/", "\\o\\", "|o|"])
```

## 内置动画

| 名称 | 内容 |
|------|------|
| `chicken`（默认） | 坤坤打篮球：运球 → 起球 → 铁山靠 → 鸡你太美 |
| `runner` | 往返奔跑的小人 |
| `rocket` | 火箭推进 |
| `spinner` | 经典转圈（UTF-8 为盲文点阵，降级为 `|/-\`） |

```python
from funny_progress import available_animations
print(available_animations())
```

## API

```python
FunProgress(total=None, desc="", animation=None, file=None, enabled=None, fps=8)
```

| 参数 | 说明 |
|------|------|
| `total` | 总步数；`None` 为不确定模式（无百分比，只显示耗时+动画） |
| `desc` | 进度条前缀描述 |
| `animation` | 动画名，默认 `chicken` |
| `file` | 输出流，默认 `sys.stderr` |
| `enabled` | `None`=自动（仅 TTY 启用）；`True`=强制；`False`=静默 |
| `fps` | 动画帧率，默认 8 |

方法：`update(n=1)` / `set_description(desc)` / `close()`，支持 `with` 上下文。

## License

MIT
