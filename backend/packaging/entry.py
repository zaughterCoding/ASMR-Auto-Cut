"""PyInstaller 的入口点。

为什么需要它：`asmr_auto_cut.cli` 里只有 `app = typer.Typer(...)` 这个对象，
没有模块级可调用入口，PyInstaller 需要一个能直接执行的脚本。
`pyproject.toml` 的 `[project.scripts]` 由 setuptools 生成控制台包装器，
冻结时那条路不存在。

内容保持三行：typer 自己会解析 sys.argv，这里不需要任何转发逻辑。
"""

from asmr_auto_cut.cli import app

app()
