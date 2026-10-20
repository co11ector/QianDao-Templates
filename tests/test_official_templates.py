import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"
sys.path.insert(0, str(ROOT / "tools"))

import normalize  # noqa: E402

OFFICIAL_PUBLIC_SLUGS = {
    "hdsky-daily-signin",
    "lwgod",
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
    "52pojie-daily-signin",
    "itsk-daily-signin",
}


def local_templates():
    return {
        path.stem: (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(LOCAL.rglob("*.har"))
    }


def published_templates():
    return {
        path.stem: (path, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((ROOT / "templates").rglob("*.har"))
    }


def test_official_public_templates_are_published_from_local():
    templates = local_templates()
    retired = json.loads((LOCAL / "retired.json").read_text(encoding="utf-8"))

    assert OFFICIAL_PUBLIC_SLUGS <= set(templates)
    assert "lwgod" in templates
    assert {"Linux_SB", "吾爱破解", "IT天空"} <= set(retired)
    assert "lwgod" not in retired
    assert {"52pojie-daily-signin", "itsk-daily-signin"} <= set(templates)
    assert not {"linux-sb-daily-signin", "lwgod-daily-login"} & set(templates)


def test_every_published_template_is_cookie_only_and_local_templates_are_included():
    published = published_templates()

    assert set(local_templates()) <= set(published)
    for slug, (path, document) in published.items():
        assert normalize.cookie_only_violation(document) is None, (slug, path)


def test_local_templates_never_reintroduce_browser_execution():
    for path, document in local_templates().values():
        encoded = json.dumps(document, ensure_ascii=False).lower()

        assert "browser://" not in encoded, path
        assert "browser_worker" not in encoded, path
        assert "browser-worker" not in encoded, path


def test_local_http_requests_pair_cookie_and_user_agent():
    for slug, (path, document) in local_templates().items():
        for step in document:
            request = step.get("request") or {}
            if not str(request.get("url") or "").startswith(("http://", "https://")):
                continue
            headers = [
                (
                    str(header.get("name") or "").casefold(),
                    str(header.get("value") or ""),
                )
                for header in request.get("headers") or []
                if isinstance(header, dict)
            ]
            cookie_headers = [value for name, value in headers if name == "cookie"]
            user_agent_headers = [
                value for name, value in headers if name == "user-agent"
            ]
            assert cookie_headers == ["{{cookie}}"], (slug, path)
            assert user_agent_headers == ["{{user_agent}}"], (slug, path)


def test_retired_browser_sites_have_fixed_host_cookie_replacements():
    for slug in ("52pojie-daily-signin", "itsk-daily-signin"):
        path, document = local_templates()[slug]
        external_urls = [
            str(step["request"].get("url") or "")
            for step in document
            if str(step.get("request", {}).get("url") or "").startswith(
                ("http://", "https://")
            )
        ]
        assert external_urls, (slug, path)
        for url in external_urls:
            netloc = urlsplit(url).netloc
            assert "{{" not in netloc and "{%" not in netloc, (slug, path, url)
        failed_patterns = " ".join(
            str(assertion.get("re") or "")
            for step in document
            for assertion in step.get("rule", {}).get("failed_asserts", [])
        )
        assert "challenge" in failed_patterns.casefold(), (slug, path)


def test_retired_browser_site_replacements_extract_one_stable_result():
    fixtures = {
        "52pojie-daily-signin": (
            '<span id="hcredit_2">42</span>',
            "42",
        ),
        "itsk-daily-signin": (
            '{"code":200,"message":"签到成功","data":{}}',
            "签到成功",
        ),
    }
    for slug, (html, expected) in fixtures.items():
        path, document = local_templates()[slug]
        extraction = next(
            item
            for step in document
            for item in step.get("rule", {}).get("extract_variables", [])
            if item.get("name") == "log_value"
        )
        pattern = re.compile(extraction["re"])
        match = pattern.search(html)
        assert pattern.groups == 1, (slug, path, extraction["re"])
        assert match is not None, (slug, path)
        assert match.group(1) == expected, (slug, path)


def test_itsk_webapi_probe_uses_one_signature_clock():
    path, document = local_templates()["itsk-daily-signin"]
    assert document[0]["request"]["url"] == "api://util/timestamp"
    extraction = document[0]["rule"]["extract_variables"]
    assert any(item.get("name") == "itsk_micro_ts" for item in extraction)

    action = document[1]["request"]
    assert action["url"] == "https://api.itsk.com/webapi/sign_activity"
    headers = {
        item["name"]: item["value"]
        for item in action["headers"]
        if isinstance(item, dict)
    }
    assert "itsk_micro_ts" in headers["X-Request-Timestamp"]
    assert "to_uuid(itsk_micro_ts)" in headers["X-Request-Nonce"]
    assert "itsk_micro_ts[0:10]" in headers["X-Request-Signature"]
    assert "|sha1" in headers["X-Request-Signature"]
    assert "itsk_access_token" in headers["Authorization"]
    assert path.name == "itsk-daily-signin.har"


def test_discuz_sign_link_extraction_accepts_html_escaped_ampersand():
    for slug in ("fnnas-forum-daily-signin", "gangzhitang-daily-signin"):
        path, document = local_templates()[slug]
        extraction = next(
            item
            for step in document
            for item in step["rule"]["extract_variables"]
            if item["name"] == "sign"
        )
        html = (
            '<a href="https://example.test/plugin.php?'
            'id=zqlj_sign&amp;sign=fixture-token">点击打卡</a>'
        )
        match = re.search(extraction["re"], html)
        assert match is not None, (slug, path)
        assert match.group(1) == "fixture-token"


def test_local_metadata_names_every_official_template():
    metadata = json.loads((LOCAL / "meta.json").read_text(encoding="utf-8"))

    assert OFFICIAL_PUBLIC_SLUGS <= set(metadata)
    assert "lwgod" in metadata
    assert all(metadata[slug].get("name") for slug in OFFICIAL_PUBLIC_SLUGS)
