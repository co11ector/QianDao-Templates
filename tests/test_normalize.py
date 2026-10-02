"""The normaliser must produce the curated layout without losing anything.

This file lives with the code it tests: with the template material kept beside the
repository it serves rather than nested inside the private QianDao checkout, the
templates repository is the versioned home of tools/normalize.py, and the workflow runs
this suite before it publishes anything.
"""

import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import normalize  # noqa: E402


def build_upstream(tmp_path, index=None):
    root = tmp_path / "upstream"
    root.mkdir()
    (root / "s1-forum.har").write_text('[{"request": {}}]', encoding="utf-8")
    (root / "leaguehd-pt.har").write_text('[{"request": {}}]', encoding="utf-8")
    (root / "broken.har").write_text("not json", encoding="utf-8")
    records = index if index is not None else [
        {"name": "S1 论坛", "filename": "s1-forum.har", "author": "Antiky",
         "url": "https://bbs.saraba1st.com/"},
        {"name": "柠檬PT", "filename": "leaguehd-pt.har", "author": "devil",
         "url": "https://leaguehd.com/attendance.php"},
        {"name": "坏文件", "filename": "broken.har", "author": "x", "url": ""},
        {"name": "无此文件", "filename": "ghost.har", "author": "x", "url": ""},
    ]
    (root / "tpls_history.json").write_text(
        json.dumps({"version": 1, "har": records}, ensure_ascii=False), encoding="utf-8"
    )
    return root


def test_templates_are_sorted_into_categories(tmp_path):
    root = build_upstream(tmp_path)
    target = tmp_path / "out"

    report = normalize.normalise(root, target)

    assert report["moved"] == 2
    assert (target / "templates" / "forum" / "s1-forum.har").is_file()
    assert (target / "templates" / "pt" / "leaguehd-pt.har").is_file()

    # Broken and missing files are reported, not silently dropped or copied.
    assert len(report["skipped"]) == 2
    assert any("broken.har" in item for item in report["skipped"])
    assert any("ghost.har" in item for item in report["skipped"])


def test_the_index_carries_the_new_paths(tmp_path):
    root = build_upstream(tmp_path)
    target = tmp_path / "out"
    normalize.normalise(root, target)

    index = json.loads((target / "tpls_history.json").read_text(encoding="utf-8"))
    records = index["har"]
    assert isinstance(records, list)
    filenames = [record["filename"] for record in records]

    assert filenames == [
        "templates/forum/s1-forum.har",
        "templates/pt/leaguehd-pt.har",
    ]
    # The app fetches <base>/<filename>, and quote() keeps the separator, so every
    # path must resolve to a file that really exists.
    for filename in filenames:
        assert (target / filename).is_file()


def test_the_mapping_index_shape_is_supported(tmp_path):
    """Upstream maps templates by name: {"har": {"<name>": {...}}}.

    The first version of this script assumed a list of records, which the list fixture
    above never contradicted; it only failed when it ran against the real repository.
    Both shapes are covered now, and the mapping shape survives on the way out.
    """
    upstream_index = {
        "晨风分享站": {"name": "晨风分享站", "filename": "s1-forum.har", "author": "loveyanglove",
                   "url": "https://raw.githubusercontent.com/qd-today/templates/master/s1-forum.har"},
        "柠檬PT签到": {"name": "柠檬PT签到", "filename": "leaguehd-pt.har", "author": "devil",
                   "url": "https://raw.githubusercontent.com/qd-today/templates/master/leaguehd-pt.har"},
    }
    root = build_upstream(tmp_path, index=upstream_index)
    target = tmp_path / "out"

    report = normalize.normalise(root, target)

    assert report["moved"] == 2
    index = json.loads((target / "tpls_history.json").read_text(encoding="utf-8"))
    assert isinstance(index["har"], dict), "the mapping shape must be preserved"
    assert set(index["har"]) == {"晨风分享站", "柠檬PT签到"}

    record = index["har"]["晨风分享站"]
    assert record["filename"] == "templates/forum/s1-forum.har"
    # The stored url points at our repository, at the published path, and is quoted.
    assert record["url"] == "%s/%s" % (
        normalize.PUBLISHED_REPOSITORY,
        quote("templates/forum/s1-forum.har"),
    )


def test_the_repository_gets_a_readme(tmp_path):
    root = build_upstream(tmp_path)
    target = tmp_path / "out"
    normalize.normalise(root, target)

    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "QianDao Templates" in readme
    assert "forum/" in readme and "pt/" in readme
    assert "brand/qiandao-templates-banner-light.png" in readme
    assert (target / "CATEGORIES.md").is_file()
