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

import json
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

PUBLISHED_REPOSITORY = "https://raw.githubusercontent.com/co11ector/QianDao-Templates/master"

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


def categorise(name: str, url: str, author: str) -> str:
    haystack = " ".join(str(part or "") for part in (name, url, author)).lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


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


def normalise(source: Path, target: Path) -> dict:
    report = {"moved": 0, "skipped": [], "categories": {}}
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

    if mapping:
        index["har"] = stored_by_name
    else:
        index["har"] = list(stored_by_name.values())
    (target / "tpls_history.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    counts = [
        "- `%s/` — %s（%d）" % (category, CATEGORY_LABELS[category], report["categories"].get(category, 0))
        for category in CATEGORY_ORDER
        if report["categories"].get(category)
    ]
    lines = [
        # The logo is the square avatar; the title sits centred directly under it.
        '<p align="center">',
        '<picture>',
        '  <source media="(prefers-color-scheme: dark)" srcset="brand/qiandao-templates-avatar-dark.png">',
        '  <img alt="QianDao Templates" src="brand/qiandao-templates-avatar-light.png" width="140">',
        '</picture>',
        '</p>',
        "",
        '<h1 align="center">QianDao Templates</h1>',
        '<p align="center">QianDao 的公共模板模块 · 上游社区模板每日自动同步并按站点类型整理</p>',
        "",
        '<p align="center">',
        '<picture>',
        '  <source media="(prefers-color-scheme: dark)" srcset="brand/qiandao-templates-banner-dark.png">',
        '  <img alt="QianDao Templates" src="brand/qiandao-templates-banner-light.png" width="100%">',
        '</picture>',
        '</p>',
        "",
        "这里的模板由上游社区仓库 `qd-today/templates` **每日自动同步并按站点类型整理**后发布，"
        "供 [QianDao](https://github.com/co11ector/QianDao) 的用户一键创建定时签到任务。",
        "",
        "仓库与本地目录单独存在只因为两件事：模板必须能被**公开抓取**（主仓是私库，"
        "而 GitHub 的可见性是仓库级的），以及让本地文件管理更清楚。",
        "",
        "## 模板数量",
        "",
        *counts,
        "",
        "## 目录结构",
        "",
        "```",
        "templates/<分类>/<模板文件>.har",
        "tpls_history.json      # 索引；filename 为相对路径，应用按 <仓库地址>/<filename> 抓取",
        "tools/normalize.py     # 整理脚本（同步流水线调用）",
        "CATEGORIES.md          # 分类规则",
        "```",
        "",
        "## 自动同步",
        "",
        "`.github/workflows/sync-upstream.yml` 每天 03:17 UTC（北京时间 11:17）自动执行：",
        "拉取上游 → 校验每个 HAR 可读 → 按关键词分类摆放 → 重新生成索引 → 提交推送。",
        "上游一有更新，本仓库会在 24 小时内跟上，无需人工干预。",
        "",
        "## 在 QianDao 中使用",
        "",
        "应用内「模板库 → 公共模板」默认订阅本仓库；也可以在「已注册仓库」里手动添加：",
        "仓库地址 `https://github.com/co11ector/QianDao-Templates`，分支 `master`。",
        "",
        "## 许可与来源",
        "",
        "- 模板**数据**镜像自上游仓库 [qd-today/templates](https://github.com/qd-today/templates)，"
        "该仓库未声明许可证，其 README 注明「项目中的模板均为开源模板，仅供学习参考使用，请勿用于商业用途」。"
        "本仓库按同样口径向个人用户提供学习参考，请勿商用。",
        "- 每个模板的**作者与出处**记录在 `tpls_history.json` 的 `author`、`comments` 与 `commenturl` 字段，"
        "权利归原作者所有；如原作者要求移除其模板，请提 issue，我们会处理。",
        "- 本仓库中的整理脚本 `tools/normalize.py` 来自 [QianDao](https://github.com/co11ector/QianDao)（MIT License，"
        "Copyright © 2021 QD-Today、2026 co11ector），与模板数据分属不同的授权范围。",
        "",
        "如发现某个模板违反你的权利或站点规则，请提 issue 说明，我们会尽快移除。",
    ]
    (target / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (target / "CATEGORIES.md").write_text(
        "\n".join(
            ["# 分类规则", ""]
            + ["- `%s` — %s" % (key, CATEGORY_LABELS[key]) for key in CATEGORY_ORDER]
            + ["", "未命中任何关键词的模板归入 `%s`。" % DEFAULT_CATEGORY]
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
    print("moved %d" % report["moved"])
    for category in CATEGORY_ORDER:
        if report["categories"].get(category):
            print("  %-8s %d" % (category, report["categories"][category]))
    for skipped in report["skipped"]:
        print("  skipped %s" % skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
