"""The normaliser must produce the curated layout without losing anything.

This file lives with the code it tests: with the template material kept beside the
repository it serves rather than nested inside the private QianDao checkout, the
templates repository is the versioned home of tools/normalize.py, and the workflow runs
this suite before it publishes anything.
"""

import base64
import json
import re
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
    normalize.normalise(root, target, local_root=tmp_path / "local")

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

    report = normalize.normalise(root, target, local_root=tmp_path / "local")

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
    normalize.normalise(root, target, local_root=tmp_path / "local")

    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "QianDao Templates" in readme
    assert "forum/" in readme and "pt/" in readme
    assert (target / "CATEGORIES.md").is_file()

    # The header is the square logo with the centred title under it. The wide banner is
    # reserved for the repository's social preview and must not appear in the readme.
    logo = readme.index("qiandao-templates-avatar-light.png")
    title = readme.index('<h1 align="center">QianDao Templates</h1>')
    assert logo < title, "the logo must sit above the centred title"
    assert "qiandao-templates-banner" not in readme
    assert readme.count("prefers-color-scheme: dark") == 1

    # The avatar carries its own wordmark, so it has to be rendered big enough to read;
    # at 140px the "TEMPLATES" line inside it was illegible.
    width = re.search(r'qiandao-templates-avatar-light\.png" width="(\d+)"', readme)
    assert width, "the logo has no explicit width"
    assert int(width.group(1)) >= 180, "the logo is too small to read its wordmark"


def test_the_readme_tells_readers_how_to_subscribe(tmp_path):
    """The readme is the only place a reader learns the address and branch to add."""
    root = build_upstream(tmp_path)
    target = tmp_path / "out"
    normalize.normalise(root, target, local_root=tmp_path / "local")

    readme = (target / "README.md").read_text(encoding="utf-8")

    assert "https://github.com/co11ector/QianDao-Templates" in readme
    assert "master" in readme
    # The app fetches <base>/<filename>; that contract is stated for anyone integrating.
    assert "<仓库地址>/<filename>" in readme


def test_the_readme_describes_categories_without_counts(tmp_path):
    """The overview explains what each directory is for; the counts are left to the app."""
    root = build_upstream(tmp_path)
    target = tmp_path / "out"
    normalize.normalise(root, target, local_root=tmp_path / "local")

    readme = (target / "README.md").read_text(encoding="utf-8")

    assert "| 目录 | 分类 | 说明 |" in readme
    # No counts: not as a column and not as a total. ("每个模板" is fine - that is prose
    # about templates, not a number.)
    assert "数量" not in readme
    assert "共 **" not in readme
    # The notes are what make the table worth reading, so at least one has to appear.
    assert any(note in readme for note in normalize.CATEGORY_NOTES.values())


def test_the_licence_section_separates_the_scopes(tmp_path):
    """Three different scopes: upstream template data, our code, our brand assets."""
    root = build_upstream(tmp_path)
    target = tmp_path / "out"
    normalize.normalise(root, target, local_root=tmp_path / "local")

    readme = (target / "README.md").read_text(encoding="utf-8")

    assert "三种不同的授权范围" in readme
    assert "| 内容 | 来源 | 授权 |" in readme
    for heading in ("### 学习用途", "### 作者与出处", "### 请求移除"):
        assert heading in readme
    # The upstream repository declares no licence, and its learning-only wording is the
    # reason we ask readers not to use the data commercially. Both facts must survive.
    assert "未声明许可证" in readme
    assert "请勿商用" in readme


def build_local(tmp_path, category="signin", name="ithome",
                comment="IT之家 每日签到（App 接口 napi.ithome.com）"):
    """A template this project maintains itself, laid out like local/<category>/<name>.har."""
    root = tmp_path / "local"
    directory = root / category
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ("%s.har" % name)).write_text(
        json.dumps(
            [
                {
                    "comment": comment,
                    "request": {
                        "method": "GET",
                        "url": "https://napi.ithome.com/api/usersign/sign?userHash={{userHash}}",
                    },
                    "rule": {
                        "success_asserts": [{"re": '"ok":(0|1)', "from": "content"}],
                        "failed_asserts": [{"re": "^(4|5)\\d\\d$", "from": "status"}],
                    },
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return root


def test_the_default_local_root_is_the_repository_local_directory():
    """The CLI has to find local/ without a flag, whatever the working directory is."""
    assert normalize.local_root_default() == (
        Path(normalize.__file__).resolve().parents[1] / "local"
    )


def test_local_templates_are_merged_and_survive_the_sync(tmp_path):
    """The whole point: templates/ is rebuilt daily, so a hand-made one must live outside it."""
    upstream = build_upstream(
        tmp_path,
        index={
            "S1 论坛": {"name": "S1 论坛", "filename": "s1-forum.har",
                        "author": "Antiky", "url": "https://bbs.saraba1st.com/"},
        },
    )
    local = build_local(tmp_path)
    target = tmp_path / "out"

    report = normalize.normalise(upstream, target, local_root=local)

    assert report["local"] == 1
    assert report["moved"] == 1

    published = target / "templates" / "signin" / "ithome.har"
    assert published.is_file()
    # Copied verbatim, so a user-facing template is never rewritten in transit.
    assert published.read_text(encoding="utf-8") == (
        local / "signin" / "ithome.har"
    ).read_text(encoding="utf-8")

    index = json.loads((target / "tpls_history.json").read_text(encoding="utf-8"))
    entry = index["har"]["ithome"]
    assert entry["author"] == normalize.LOCAL_AUTHOR
    assert entry["filename"] == "templates/signin/ithome.har"
    assert entry["url"] == (
        "https://raw.githubusercontent.com/co11ector/QianDao-Templates/"
        "master/templates/signin/ithome.har"
    )
    # The app shows comments in the template list, so the first step's comment is carried
    # through as instructions for the variable the user has to fill in.
    assert entry["comments"].startswith("IT之家 每日签到")
    # The body is embedded like the upstream records do, so importing one of our
    # templates does not need a second fetch of the published file.
    assert json.loads(base64.b64decode(entry["content"]).decode("utf-8"))[0]["request"][
        "url"
    ].endswith("?userHash={{userHash}}")
    # The app decides whether to re-import with `int(current["version"]) < int(new)`, so
    # a record whose version is missing or non-numeric raises and aborts the refresh for
    # every user - this was a real regression when the merge first shipped.
    assert entry["version"].isdigit()
    assert entry["date"]
    assert isinstance(entry["update"], int)
    # commenturl is where the app sends people who press 评论. Every upstream record is a
    # /issues/ link; ours was the template file at first, which made the button dump raw
    # JSON at the reader.
    assert "/issues/" in entry["commenturl"]
    assert entry["commenturl"] != entry["url"]
    assert entry["commenturl"] == normalize.LOCAL_COMMENT_URL
    # And it must move forward when the template changes, or updates would never land.
    assert entry["version"].startswith(entry["date"][:4] + entry["date"][5:7] + entry["date"][8:10])
    # No credential may ever travel with a published template: the placeholder is all
    # there is, and the real value lives only in the user's own task. The prose may say
    # "Bearer prefix", so look for a token actually stuck to it.
    assert not re.search(r"Bearer\S{20,}", json.dumps(entry, ensure_ascii=False))

    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "本项目自有的模板" in readme
    assert "templates/signin/ithome.har" in readme


def test_a_mapped_comment_url_wins_over_the_request_board(tmp_path):
    """Each template gets its own 评论区 issue, like the upstream repository does."""
    upstream = build_upstream(
        tmp_path,
        index={
            "S1 论坛": {"name": "S1 论坛", "filename": "s1-forum.har",
                        "author": "Antiky", "url": "https://bbs.saraba1st.com/"},
        },
    )
    local = build_local(tmp_path)
    (local / "meta.json").write_text(
        json.dumps({
            "ithome": {
                "name": "IT之家",
                "commenturl": "https://github.com/co11ector/QianDao-Templates/issues/2",
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    target = tmp_path / "out"

    normalize.normalise(upstream, target, local_root=local)

    index = json.loads((target / "tpls_history.json").read_text(encoding="utf-8"))
    # The display name comes from the metadata file, while the file keeps its stable
    # ASCII name: the app's identity is (name, repo, url, branch), so a rename here is a
    # one-off that leaves the old row behind, not something to do casually.
    assert "IT之家" in index["har"]
    assert index["har"]["IT之家"]["filename"] == "templates/signin/ithome.har"
    assert index["har"]["IT之家"]["commenturl"].endswith("/issues/2")


def test_a_local_template_wins_over_an_upstream_name(tmp_path):
    """If the names collide the maintained one is the one that ships, and it is reported."""
    upstream = build_upstream(
        tmp_path,
        index={
            "ithome": {"name": "ithome", "filename": "s1-forum.har",
                       "author": "someone", "url": "https://example.invalid/"},
        },
    )
    local = build_local(tmp_path)
    target = tmp_path / "out"

    report = normalize.normalise(upstream, target, local_root=local)

    assert report["overridden"] == ["ithome"]
    index = json.loads((target / "tpls_history.json").read_text(encoding="utf-8"))
    assert index["har"]["ithome"]["author"] == normalize.LOCAL_AUTHOR


def test_an_unreadable_local_template_is_reported_not_published(tmp_path):
    upstream = build_upstream(tmp_path)
    local = tmp_path / "local"
    (local / "signin").mkdir(parents=True)
    (local / "signin" / "broken.har").write_text("not json", encoding="utf-8")
    (local / "signin" / "empty.har").write_text("[]", encoding="utf-8")
    target = tmp_path / "out"

    report = normalize.normalise(upstream, target, local_root=local)

    assert report["local"] == 0
    assert not (target / "templates" / "signin" / "broken.har").exists()
    assert any("local/signin/broken.har" in item for item in report["skipped"])
    assert any("local/signin/empty.har" in item for item in report["skipped"])



def test_records_sharing_a_filename_collapse_to_the_newest():
    """Upstream publishes one template twice, once with .har in the name.

    The application keys a subscription by filename, so two records for one file become two
    library rows and a duplicate in the public list - and the older one can never be displaced
    while the index keeps offering it.
    """
    stored = {
        "\u8fc5\u7ef4\u7f51": {"filename": "templates/signin/\u8fc5\u7ef4\u7f51.har", "version": "20220302"},
        "\u8fc5\u7ef4\u7f51.har": {"filename": "templates/signin/\u8fc5\u7ef4\u7f51.har", "version": "20260425"},
        "\u522b\u7684": {"filename": "templates/signin/\u522b\u7684.har", "version": "20240101"},
    }

    kept, dropped = normalize.dedupe_by_filename(stored)

    assert set(kept) == {"\u8fc5\u7ef4\u7f51.har", "\u522b\u7684"}
    assert dropped == ["\u8fc5\u7ef4\u7f51"]
    assert kept["\u8fc5\u7ef4\u7f51.har"]["version"] == "20260425"


def test_the_newest_version_wins_whatever_the_order():
    older = {"filename": "a.har", "version": "20200101"}
    newer = {"filename": "a.har", "version": "20260101"}

    assert set(normalize.dedupe_by_filename({"old": older, "new": newer})[0]) == {"new"}
    assert set(normalize.dedupe_by_filename({"new": newer, "old": older})[0]) == {"new"}


def test_a_record_without_a_version_does_not_displace_a_dated_one():
    kept, dropped = normalize.dedupe_by_filename({
        "dated": {"filename": "a.har", "version": "20260101"},
        "undated": {"filename": "a.har"},
    })

    assert set(kept) == {"dated"}
    assert dropped == ["undated"]


def test_records_for_different_files_are_untouched():
    kept, dropped = normalize.dedupe_by_filename({
        "one": {"filename": "a.har", "version": "20260101"},
        "two": {"filename": "b.har", "version": "20260101"},
    })

    assert set(kept) == {"one", "two"}
    assert dropped == []


def test_the_written_index_holds_one_record_per_filename(tmp_path):
    """The dedupe must reach the written file, not just the mapping it works on.

    Its first version collapsed the local variable after index["har"] had already been assigned
    to it, so the unit test passed while the published index still carried both records.
    """
    records = [
        {"name": "\u8fc5\u7ef4\u7f51", "filename": "s1-forum.har", "author": "x", "url": "",
         "version": "20220302"},
        {"name": "\u8fc5\u7ef4\u7f51.har", "filename": "s1-forum.har", "author": "x", "url": "",
         "version": "20260425"},
    ]
    root = build_upstream(tmp_path, index=records)
    target = tmp_path / "out"

    report = normalize.normalise(root, target, local_root=tmp_path / "local")

    written = json.loads((target / "tpls_history.json").read_text(encoding="utf-8"))["har"]
    if isinstance(written, dict):
        written = list(written.values())
    # The category comes from the classifier, so only the file and the count are asserted here.
    assert len(written) == 1
    assert written[0]["filename"].endswith("s1-forum.har")
    assert written[0]["version"] == "20260425"
    assert report["deduped"] == ["\u8fc5\u7ef4\u7f51"]
