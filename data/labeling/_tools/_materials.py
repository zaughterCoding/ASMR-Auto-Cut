"""素材登记表：目录、源文件、标注配额。

**这份文件是读取器，本身不含任何素材数据。** 具体的素材——源文件路径、标题、
配额——放在同级目录的 `_materials.local.json` 里，那份不进版本管理：它记的是
本地媒体库的绝对路径和作品名，属于个人数据。

首次使用：把 `_materials.example.json` 复制成 `_materials.local.json`，填上
自己的素材再跑。

local.json 的结构：

    {
      "default": "<不给素材名时用哪个，可以不设>",
      "materials": {
        "<素材名>": {
          "title": "<显示用，随便写>",
          "lang": "ja",
          "src": "<源文件绝对路径>",
          "plan": {"keep": 40, "talk": 50, "inactive": 10},
          "seed": 20260101,
          "min_region_seconds": 1.0,
          "note": "<可选，自由文本>"
        }
      }
    }

目录约定（以后加素材照这个来）：

    data/labeling/
        _tools/                  脚本都在这儿，不跟素材混在一起
        <语种>/<素材>/
            clips/               抽出来待标注的片段（顺序已打乱）
            labels.csv           人工标注，**只有这一份是人的成果，别覆盖**
            _answer_key.csv      答案对照表，标注期间不许打开
            README.md            这个素材是什么（含数据信息，不进版本管理）
            怎么标注.md           判定规则，以及这个素材特有的补充（可选）

语种用 ISO 639-1 两字母：ja / zh / ko。

路径写在 json 里而不是从命令行传，是为了绕开 Windows 下 shell 传中日韩/带 #
的路径时的编码问题：Python 直接从文件读，不经过 shell。
"""

import json
from pathlib import Path

#: 本文件在 data/labeling/_tools/ 下，往上四层才是仓库根。
#: （搬进 _tools/ 之前是 parents[2]，加了一层目录就要跟着改。）
ROOT = Path(__file__).resolve().parents[3]
LABELING = ROOT / "data" / "labeling"

#: 本地素材登记表。不进版本管理，见模块 docstring。
LOCAL = Path(__file__).with_name("_materials.local.json")
EXAMPLE = Path(__file__).with_name("_materials.example.json")

_registry: dict | None = None


def _read_local() -> dict:
    if not LOCAL.exists():
        raise SystemExit(
            f"没有本地素材登记表：{LOCAL}\n"
            f"把 {EXAMPLE.name} 复制成 {LOCAL.name}，填上自己的素材再跑。"
        )
    try:
        return json.loads(LOCAL.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"{LOCAL} 不是合法 JSON：{error}") from error


def registry() -> dict:
    """local.json 的内容。读一次就缓存，不给每处调用都摊一次 IO。"""
    global _registry
    if _registry is None:
        _registry = _read_local()
    return _registry


def materials() -> dict[str, dict]:
    """素材名 -> 素材信息。src 已经转成 Path。"""
    raw = registry().get("materials") or {}
    return {name: {**item, "src": Path(item["src"])} for name, item in raw.items()}


def default_name() -> str | None:
    """不给素材名时用哪个。登记表里没设就是 None。"""
    return registry().get("default")


def label_dir(name: str) -> Path:
    """素材的标注目录。键 == 目录名，所以这里不用再维护一份映射。"""
    return LABELING / materials()[name]["lang"] / name


def project_dir(material: dict) -> Path:
    """分析结果目录。名字取自源文件名（不含所在文件夹），和标注目录不是一回事。"""
    return ROOT / "data" / "projects" / material["src"].stem


def load(name: str | None) -> tuple[str, dict]:
    """按名字取素材，顺带把 out 填好。

    支持唯一前缀匹配——`example` 能指到 `example_20260101`，命令行里少打几个字。
    模糊到匹配上多个就报错列出来，不猜。
    """
    known = materials()
    if name is None:
        name = default_name()
        if name is None:
            raise SystemExit(
                "没给素材名，登记表里也没设 default。用法：<脚本> <素材名>\n"
                f"可用：{', '.join(sorted(known))}"
            )
    if name in known:
        key = name
    else:
        hits = [k for k in known if k.startswith(name)]
        if not hits:
            raise SystemExit(f"没有这个素材：{name}\n可用：{', '.join(sorted(known))}")
        if len(hits) > 1:
            raise SystemExit(f"「{name}」匹配到多个素材，写全：{', '.join(sorted(hits))}")
        key = hits[0]
    return key, {**known[key], "out": label_dir(key)}
