import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"

OFFICIAL_BUILTIN_SLUGS = {
    "hdsky-daily-signin",
    "3dm-daily-login-reward",
    "fnnas-forum-daily-signin",
    "ymlyhd-daily-signin",
    "bilibili-daily-suite",
    "right-forum-daily-signin",
    "huorong-forum-daily-login",
    "chiphell-daily-login",
    "pcbeta-daily-login",
    "koolcenter-daily-login",
    "smzdm-daily-signin",
    "hdduck-daily-signin",
    "ali213-daily-signin",
    "10001-daily-login",
    "sglynp-daily-login",
    "acgrip-daily-signin",
    "bookmarkmars-daily-login",
    "ssdforum-daily-signin",
    "ptshare-daily-signin",
    "gangzhitang-daily-signin",
}


def local_templates():
    return {
        path.stem: (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(LOCAL.rglob("*.har"))
    }


def test_official_builtin_templates_are_published_from_local():
    templates = local_templates()
    retired = json.loads((LOCAL / "retired.json").read_text(encoding="utf-8"))

    assert OFFICIAL_BUILTIN_SLUGS <= set(templates)
    assert "lwgod" not in templates
    assert {"lwgod", "Linux_SB", "吾爱破解", "IT天空"} <= set(retired)
    assert not {
        "linux-sb-daily-signin",
        "lwgod-daily-login",
        "52pojie-daily-signin",
        "itsk-daily-signin",
    } & set(templates)


def test_local_templates_never_reintroduce_browser_execution():
    for path, document in local_templates().values():
        encoded = json.dumps(document, ensure_ascii=False).lower()

        assert "browser://" not in encoded, path
        assert "browser_worker" not in encoded, path
        assert "browser-worker" not in encoded, path


def test_cookie_builtin_requests_pair_cookie_and_user_agent():
    for slug, (path, document) in local_templates().items():
        if slug not in OFFICIAL_BUILTIN_SLUGS:
            continue
        encoded = json.dumps(document, ensure_ascii=False).lower()
        if "{{cookie" not in encoded:
            continue

        for step in document:
            request = step.get("request") or {}
            if not str(request.get("url") or "").startswith(("http://", "https://")):
                continue
            headers = {
                str(header.get("name") or "").casefold(): str(header.get("value") or "")
                for header in request.get("headers") or []
                if isinstance(header, dict)
            }
            assert headers.get("cookie") == "{{cookie}}", (slug, path)
            assert headers.get("user-agent") == "{{user_agent}}", (slug, path)


def test_local_metadata_names_every_official_template():
    metadata = json.loads((LOCAL / "meta.json").read_text(encoding="utf-8"))

    assert OFFICIAL_BUILTIN_SLUGS <= set(metadata)
    assert "lwgod" not in metadata
    assert all(metadata[slug].get("name") for slug in OFFICIAL_BUILTIN_SLUGS)
