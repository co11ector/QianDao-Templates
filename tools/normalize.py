#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""Turn an upstream template repository into the curated layout we publish.

This file belongs to the QianDao Templates folder: it is the canonical copy of the
normaliser that co11ector/QianDao-Templates runs in GitHub Actions. A copy of it lives
in that repository at tools/normalize.py, because the workflow there cannot reach into
our private main repository.

qd-today/templates keeps every .har at the repository root and describes them in
tpls_history.json, whose "har" member is a mapping of template name to record. That is
fine as a drop-off point and hard to read as a repository, and it mixes forum trackers,
private trackers and video sites in one flat list.

This script produces the layout we publish:

    templates/<category>/<original filename>.har
    tpls_history.json   (same records; filename carries the category path, url points
                         at our repository rather than upstream)

It is deliberately conservative about names: upstream filenames are referenced by the
app's records and by operators, so files are moved, never renamed. Files that are not
readable JSON, and files the index points at but that are absent, are skipped and
reported, so one broken upload cannot stop a sync. The app fetches as
<base>/<filename>, and urllib quote keeps the separator, so a path in the index
resolves exactly like a root-level file did.
"""

import base64
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

PUBLISHED_REPOSITORY = "https://raw.githubusercontent.com/co11ector/QianDao-Templates/master"
# Shown as the author of the templates this project writes itself, under local/.
LOCAL_AUTHOR = "QianDao"

CATEGORY_KEYWORDS = (
    ("pt", ("pt", "torrent", "seed", "leaguehd", "hdsky", "柠檬", "pt站")),
    ("forum", ("forum", "bbs", "discuz", "论坛", "破解", "精易", "saraba", "chiphell")),
    ("video", ("bili", "video", "视频", "音乐", "163", "acfun")),
    ("shop", ("shop", "jd", "taobao", "购物")),
)
DEFAULT_CATEGORY = "signin"
CATEGORY_ORDER = ("pt", "forum", "video", "shop", "signin")
CATEGORY_LABELS = {
    "pt": "PT 站",
    "forum": "论坛社区",
    "video": "影音",
    "shop": "购物",
    "signin": "通用签到",
}
# What belongs in each directory. The readme describes the categories rather than
# counting them: a number that changes daily is noise for a reader deciding where to look.
CATEGORY_NOTES = {
    "pt": "需要登录的私有 PT 站，多为签到与保号类任务",
    "forum": "Discuz、Flarum 等论坛的每日签到与打卡",
    "video": "视频与音乐站点的签到、试听与日常任务",
    "shop": "电商与购物类站点的签到、领券与日常任务",
    "signin": "其余站点；未命中上面关键词的都归到这里",
}


def categorise(name: str, url: str, author: str) -> str:
    haystack = " ".join(str(part or "") for part in (name, url, author)).lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


def local_root_default() -> Path:
    """The repository's own hand-maintained templates: <repo>/local/<category>/*.har."""
    return Path(__file__).resolve().parent.parent / "local"


def local_record_metadata(path: Path, published_url: str) -> dict:
    """The version/date/update/commenturl fields the application expects on a record.

    version must be an int-comparable date because the app decides whether to re-import
    with `int(current["version"]) < int(template["version"])`, and a record without it
    raises and aborts the whole refresh for every user. Git's last commit date for the
    file keeps the value stable across checkouts - the file mtime does not, and the daily
    workflow would then emit a new index every run - while still moving forward whenever
    the template is actually edited. Outside a work tree it falls back to the mtime.
    """
    stamp = None
    try:
        completed = subprocess.run(
            ["git", "log", "-1", "--format=%cd", "--date=format:%Y%m%d%H%M%S", "--", str(path)],
            cwd=str(path.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        raw = completed.stdout.strip()
        if completed.returncode == 0 and raw:
            stamp = datetime.datetime.strptime(raw, "%Y%m%d%H%M%S")
    except (OSError, ValueError):
        stamp = None
    if stamp is None:
        stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime)
    return {
        "version": stamp.strftime("%Y%m%d"),
        "date": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "update": int(stamp.timestamp()),
        "commenturl": published_url,
    }


def read_local_entries(local_root: Path):
    """Yield (path, category) for the templates this project maintains itself.

    The daily sync rebuilds templates/ and tpls_history.json from upstream, so a template
    dropped into templates/ by hand disappears on the next run. Anything under
    local/<category>/ is merged into that output instead, in category order so the
    generated index stays stable between runs.
    """
    if local_root is None or not Path(local_root).is_dir():
        return
    for category in CATEGORY_ORDER:
        directory = Path(local_root) / category
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.har")):
            yield path, category


def read_har_entries(source: Path):
    """Yield (record, category) for every template the index points at.

    The upstream index maps each template by name, {"har": {"<name>": {...}}}; older
    copies used a list of records, so both shapes are accepted.
    """
    index_path = source / "tpls_history.json"
    if not index_path.exists():
        raise SystemExit("no tpls_history.json in %s" % source)

    index = json.loads(index_path.read_text(encoding="utf-8"))
    records = index.get("har") or {}
    iterable = list(records.values()) if isinstance(records, dict) else list(records)
    for record in iterable:
        if not isinstance(record, dict):
            continue
        filename = record.get("filename") or ""
        name = record.get("name") or filename
        yield record, categorise(name, record.get("url") or "", record.get("author") or "")


def normalise(source: Path, target: Path, local_root=None) -> dict:
    report = {
        "moved": 0,
        "local": 0,
        "skipped": [],
        "overridden": [],
        "categories": {},
        "local_templates": [],
    }
    if target.exists():
        shutil.rmtree(target)
    (target / "templates").mkdir(parents=True)

    index = json.loads((source / "tpls_history.json").read_text(encoding="utf-8"))
    records = index.get("har")
    mapping = isinstance(records, dict)
    stored_by_name = {}

    for record, category in read_har_entries(source):
        filename = record.get("filename") or ""
        source_file = source / filename
        if not source_file.is_file():
            source_file = source / filename.lstrip("/")
        if not source_file.is_file():
            report["skipped"].append("%s: missing" % filename)
            continue
        try:
            json.loads(source_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            report["skipped"].append(
                "%s: unreadable (%s)" % (filename, error.__class__.__name__)
            )
            continue

        relative = "templates/%s/%s" % (category, source_file.name)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)

        stored = dict(record)
        stored["filename"] = relative
        # The record kept the upstream raw URL, which pointed at the repository root.
        # Ours lives under the category, and non-ASCII names have to be quoted, so the
        # stored url is rebuilt from the published path rather than the bare filename.
        stored["url"] = "%s/%s" % (PUBLISHED_REPOSITORY, quote(relative))
        stored_by_name[record.get("name") or source_file.name] = stored
        report["moved"] += 1
        report["categories"].setdefault(category, 0)
        report["categories"][category] += 1

    # Merge the templates this project maintains itself. They are copied verbatim and
    # indexed like the upstream ones, except that the category comes from the directory
    # rather than from keyword matching, and a local name wins over an upstream one.
    resolved_local_root = (
        local_root_default() if local_root is None else Path(local_root)
    )
    for path, category in read_local_entries(resolved_local_root):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            report["skipped"].append(
                "local/%s/%s: unreadable (%s)"
                % (category, path.name, error.__class__.__name__)
            )
            continue
        if not isinstance(document, list) or not document:
            report["skipped"].append(
                "local/%s/%s: not a non-empty JSON array"
                % (category, path.name)
            )
            continue

        comment = ""
        first = document[0]
        if isinstance(first, dict):
            comment = str(first.get("comment") or "")

        name = path.stem
        relative = "templates/%s/%s" % (category, path.name)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)

        if name in stored_by_name:
            report["overridden"].append(name)
        published_url = "%s/%s" % (PUBLISHED_REPOSITORY, quote(relative))
        stored_by_name[name] = {
            "name": name,
            "filename": relative,
            "url": published_url,
            "author": LOCAL_AUTHOR,
            "comments": comment,
            # Upstream records embed the template body and the app uses it when present.
            # Embedding ours too means importing one of our templates does not depend on
            # a second fetch of the published file, which is the step that already proved
            # unreliable from the NAS.
            "content": base64.b64encode(path.read_bytes()).decode("ascii"),
            **local_record_metadata(path, published_url),
        }
        report["local"] += 1
        report["local_templates"].append((name, relative))
        report["categories"].setdefault(category, 0)
        report["categories"][category] += 1

    if mapping:
        index["har"] = stored_by_name
    else:
        index["har"] = list(stored_by_name.values())

    (target / "tpls_history.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    structure_rows = [
        "| [`%s/`](templates/%s) | %s | %s |"
        % (category, category, CATEGORY_LABELS[category], CATEGORY_NOTES[category])
        for category in CATEGORY_ORDER
        if report["categories"].get(category)
    ]
    lines = [
        # The header is the square logo with the title centred directly under it. The wide
        # banner is deliberately not shown here: it belongs to the repository's social
        # preview, which is where a 2:1 image is wanted.
        '<p align="center">',
        '<picture>',
        '  <source media="(prefers-color-scheme: dark)" srcset="brand/qiandao-templates-avatar-dark.png">',
        '  <img alt="QianDao Templates" src="brand/qiandao-templates-avatar-light.png" width="200">',
        '</picture>',
        '</p>',
        "",
        '<h1 align="center">QianDao Templates</h1>',
        '<p align="center">QianDao 的公共模板模块 · 上游社区模板每日自动同步并按站点类型整理</p>',
        "",
        "「QianDao 自动化运行台」的**公共模板模块**：把上游社区仓库 `qd-today/templates` 的模板"
        "每天自动同步、校验并按站点类型整理，供 [QianDao](https://github.com/co11ector/QianDao)"
        " 的用户一键创建定时签到任务。",
        "",
        "- **开箱可用**：订阅本仓库即可在应用内挑选模板，不必自己收集",
        "- **每日更新**：上游一有变化，24 小时内自动跟上",
        "- **整理清楚**：按站点类型分目录，索引与文件一一对应",
        "- **来源可查**：每个模板的作者与出处都保留在索引里",
        "",
        "仓库与本地目录单独存在只因为两件事：模板必须能被**公开抓取**（主仓是私库，"
        "而 GitHub 的可见性是仓库级的），以及让本地文件管理更清楚。",
        "",
        "## 模板分类",
        "",
        "模板按站点类型分目录摆放，应用内「模板库 → 公共模板」可以直接搜索与订阅：",
        "",
        "| 目录 | 分类 | 说明 |",
        "| --- | --- | --- |",
        *structure_rows,
        "",
        "完整列表见 [`tpls_history.json`](tpls_history.json)：索引里 `filename` 为相对路径，"
        "`url` 指向本仓库，应用按 `<仓库地址>/<filename>` 抓取。",
        "",
        *(
            [
                "其中 **%d 个是本项目自有的模板**（放在 `local/` 下，每日同步不会覆盖）："
                % report["local"],
                "",
                "| 模板 | 位置 |",
                "| --- | --- |",
                *[
                    "| %s | [`%s`](%s) |" % (name, relative, relative)
                    for name, relative in report["local_templates"]
                ],
                "",
            ]
            if report["local"]
            else []
        ),
        "## 自动同步",
        "",
        "`.github/workflows/sync-upstream.yml` 每天 **03:17 UTC（北京时间 11:17）** 自动执行，"
        "也可以手动触发：",
        "",
        "1. 先跑整理脚本的测试 —— **不通过就中止**，不会发布被改坏的索引；",
        "2. 浅克隆上游仓库；",
        "3. 校验每个 HAR 能否解析，按关键词分类，重写索引里的路径与直链；",
        "4. 重新生成 README 与 CATEGORIES，有变化才提交推送。",
        "",
        "全程使用仓库内置的 `GITHUB_TOKEN`，**不需要个人访问令牌**。",
        "",
        "## 在 QianDao 中使用",
        "",
        "应用内「模板库 → 公共模板」**默认已订阅本仓库**，打开即可搜索与订阅。",
        "若要手动添加，在「已注册仓库」里按下面的值填写：",
        "",
        "```",
        "仓库名     default（随意，用于在列表里区分）",
        "仓库地址   https://github.com/co11ector/QianDao-Templates",
        "分支       master",
        "```",
        "",
        "添加后点一次「**强制更新**」即可拉到最新模板。本仓库每天自动同步上游，" 
        "所以之后刷新模板列表取到的就是最新内容，不必反复手动更新。",
        "",
        "## 许可与来源",
        "",
        "本仓库的内容分属**三种不同的授权范围**，请分别看待：",
        "",
        "| 内容 | 来源 | 授权 |",
        "| --- | --- | --- |",
        "| `templates/` 模板数据、`tpls_history.json` 索引 | 上游 [qd-today/templates](https://github.com/qd-today/templates) | 上游**未声明许可证** |",
        "| `tools/`、`tests/`、`.github/`、`docs/` | 本项目（[QianDao](https://github.com/co11ector/QianDao)） | MIT License，Copyright © 2021 QD-Today、2026 co11ector |",
        "| `brand/` 品牌资产 | 本项目（[QianDao](https://github.com/co11ector/QianDao)） | 同上（MIT） |",
        "",
        "### 学习用途",
        "",
        "上游 README 注明「项目中的模板均为开源模板，仅供学习参考使用，请勿用于商业用途」。"
        "本仓库按同样口径提供，**仅供个人学习参考，请勿商用**。",
        "",
        "### 作者与出处",
        "",
        "每个模板的 `author`、`comments`、`commenturl` 都保留在 "
        "[`tpls_history.json`](tpls_history.json) 里，**权利归原作者所有**。"
        "本仓库只做同步、校验与整理，不对模板数据主张任何权利。",
        "",
        "### 请求移除",
        "",
        "如果某个模板侵犯了你的权利、违反所在站点的规则，或你作为原作者希望移除它，"
        "请提 issue 说明，我们会尽快处理。",
        "",
        "## 反馈与求模板",
        "",
        "- **求模板**：用[模板请求表单](https://github.com/co11ector/QianDao-Templates/issues/new?template=template-request.yml)"
        "提交（填站点名称、地址、是否需要登录即可）；也可以直接在[模板请求板]"
        "(https://github.com/co11ector/QianDao-Templates/issues/1)下面留言。",
        "- **想自己动手**：应用内有 HAR 编辑器，抓包导出 `.har` 后可以向上游社区仓库提 PR，"
        "同步后这里也会跟着更新。",
        "- **分类不合适 / 模板已失效 / 其他建议**：同样提 issue 说明即可。",
    ]
    (target / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (target / "CATEGORIES.md").write_text(
        "\n".join(
            [
                "# 分类规则",
                "",
                "整理脚本按**模板名、来源地址与作者**里的关键词判断归属；未命中任何关键词的模板"
                "归入 `%s/`。规则写在 `tools/normalize.py` 的 `CATEGORY_KEYWORDS` 里，"
                "改完在下次同步生效。" % DEFAULT_CATEGORY,
                "",
                "| 目录 | 说明 |",
                "| --- | --- |",
            ]
            + ["| `%s/` | %s |" % (key, CATEGORY_LABELS[key]) for key in CATEGORY_ORDER]
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def main(argv):
    if len(argv) != 3:
        print("usage: normalize.py <source> <target>")
        return 2
    report = normalise(Path(argv[1]), Path(argv[2]))
    print("moved %d (%d local)" % (report["moved"], report["local"]))
    for name, relative in report["local_templates"]:
        print("  local %s -> %s" % (name, relative))
    for name in report["overridden"]:
        print("  local override %s" % name)
    for category in CATEGORY_ORDER:
        if report["categories"].get(category):
            print("  %-8s %d" % (category, report["categories"][category]))
    for skipped in report["skipped"]:
        print("  skipped %s" % skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))