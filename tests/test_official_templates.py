import json
import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlsplit

from jinja2.sandbox import SandboxedEnvironment

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


def rendered_rule_pattern(pattern, **variables):
    environment = SandboxedEnvironment()

    def date_time(date=True, time=True, time_difference=0):
        del time_difference
        if date and time:
            return "2026-10-22 18:00:00"
        if date:
            return "2026-10-22"
        if time:
            return "18:00:00"
        return ""

    environment.globals["date_time"] = date_time
    environment.filters["date_time"] = date_time
    rendered = environment.from_string(pattern).render(**variables)
    delimited = re.fullmatch(r"/(.*)/([imsu]*)", rendered, re.S)
    if not delimited:
        return re.compile(rendered)

    flags = 0
    for modifier, flag in (
        ("i", re.I),
        ("m", re.M),
        ("s", re.S),
        ("u", re.U),
    ):
        if modifier in delimited.group(2):
            flags |= flag
    return re.compile(delimited.group(1), flags)


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


def test_every_local_template_has_an_operator_guidance_header():
    for slug, (path, document) in local_templates().items():
        comments = [
            str(step.get("comment") or "").strip()
            for step in document
            if isinstance(step, dict)
        ]
        assert any(comments), (slug, path)


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


def test_fnnas_uses_the_edge_tls_profile_that_owns_its_cookie_pair():
    path = LOCAL / "forum" / "fnnas-forum-daily-signin.har"
    document = json.loads(path.read_text(encoding="utf-8"))
    external = [
        step["request"]
        for step in document
        if str(step.get("request", {}).get("url") or "").startswith(
            ("http://", "https://")
        )
    ]

    assert external
    for request in external:
        headers = {
            str(header.get("name") or "").casefold(): str(
                header.get("value") or ""
            )
            for header in request.get("headers") or []
        }
        assert headers.get("x-qiandao-impersonate") == "edge", path


def test_transport_fingerprint_sensitive_templates_use_the_edge_tls_profile():
    for slug in (
        "52pojie-daily-signin",
        "pcbeta-daily-login",
        "ali213-daily-signin",
    ):
        path, document = local_templates()[slug]
        external = [
            step["request"]
            for step in document
            if str(step.get("request", {}).get("url") or "").startswith(
                ("http://", "https://")
            )
        ]

        assert external, path
        for request in external:
            headers = {
                str(header.get("name") or "").casefold(): str(
                    header.get("value") or ""
                )
                for header in request.get("headers") or []
            }
            assert headers.get("x-qiandao-impersonate") == "edge", path


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


def test_fnnas_authenticated_footer_login_link_is_not_a_login_failure():
    path, document = local_templates()["fnnas-forum-daily-signin"]
    first_step = document[0]
    html = (
        '<a href="member.php?mod=logging&amp;action=logout">退出</a>'
        '<a href="member.php?mod=logging&amp;action=login">登录</a>'
        '<a href="plugin.php?id=zqlj_sign&amp;sign=fixture-token">'
        "点击打卡</a>"
    )

    success = first_step["rule"]["success_asserts"][0]["re"]
    assert re.search(success, html, re.S | re.I), path
    for assertion in first_step["rule"]["failed_asserts"]:
        assert re.search(assertion["re"], html) is None, (path, assertion)


def test_fnnas_requires_an_explicit_signin_result_and_rejects_alert_info_login():
    path, document = local_templates()["fnnas-forum-daily-signin"]
    submit_step = document[2]
    success_patterns = [
        assertion["re"] for assertion in submit_step["rule"]["success_asserts"]
    ]
    alert_failure_patterns = [
        assertion["re"]
        for assertion in submit_step["rule"]["failed_asserts"]
        if "messagetext" in assertion["re"]
    ]
    success_html = (
        '<div id="messagetext" class="alert_info">'
        "<p>打卡成功，获得飞牛币。</p></div>"
    )
    login_html = (
        '<div id="messagetext" class="alert_info">'
        "<p>请登录后继续操作</p></div>"
    )

    assert any(re.search(pattern, success_html) for pattern in success_patterns), path
    assert not any(re.search(pattern, login_html) for pattern in success_patterns), path
    assert alert_failure_patterns, path
    assert any(
        re.search(pattern, login_html) for pattern in alert_failure_patterns
    ), path


def test_fnnas_extracts_only_the_visible_signin_message():
    _path, document = local_templates()["fnnas-forum-daily-signin"]
    submit_step = document[2]
    extraction = next(
        item
        for item in submit_step["rule"]["extract_variables"]
        if item["name"] == "status_message"
    )
    html = (
        '<div id="messagetext" class="alert_info">'
        '<p>恭喜您，打卡成功！<script type="text/javascript">'
        "window.location.reload();</script></p></div>"
    )

    match = re.search(extraction["re"], html, re.S | re.I)
    assert match is not None
    assert match.group(1) == "恭喜您，打卡成功！"


def test_authenticated_discuz_pages_do_not_trip_generic_challenge_words():
    fixtures = {
        "hdsky-daily-signin": (
            '<a href="member.php?mod=logging&amp;action=logout">退出</a>'
            '<a href="member.php?mod=logging&amp;action=login">登录</a>'
            '<script>const deferredCaptcha = "captcha"; '
            'const retiredChallenge = "Cloudflare challenge 验证码 滑块";</script>'
        ),
        "fnnas-forum-daily-signin": (
            '<a href="member.php?mod=logging&amp;action=logout">退出</a>'
            '<a href="member.php?mod=logging&amp;action=login">登录</a>'
            '<a href="plugin.php?id=zqlj_sign&amp;sign=fixture-token">'
            "点击打卡</a>"
            '<script>const deferredCaptcha = "captcha"; '
            'const retiredChallenge = "安全验证 滑块 异常请求";</script>'
        ),
        "52pojie-daily-signin": (
            '<a href="space-uid-42.html" id="m">fixture-user</a>'
            '<a href="member.php?mod=logging&amp;action=login">登录</a>'
            '<script>const deferredCaptcha = "captcha"; '
            'const retiredChallenge = "WZWS challenge 验证码 Cloudflare";</script>'
        ),
        "hdduck-daily-signin": (
            '<a href="member.php?mod=logging&amp;action=logout">退出</a>'
            '<input type="hidden" name="formhash" value="fixture123">'
            "<h1>您今天已经签到过了或者签到时间还未开始</h1>"
            '<script src="//static.cloudflareinsights.com/beacon.min.js"></script>'
        ),
    }
    for slug, html in fixtures.items():
        path, document = local_templates()[slug]
        for assertion in document[0]["rule"]["failed_asserts"]:
            assert re.search(assertion["re"], html, re.S) is None, (
                slug,
                path,
                assertion,
            )


def test_hdduck_last_signin_time_uses_a_date_only_pattern():
    path, document = local_templates()["hdduck-daily-signin"]
    html = (
        '<a href="member.php?mod=logging&amp;action=logout">退出</a>'
        "<script>discuz_uid = '42';</script>"
        "<h1>您今天已经签到过了或者签到时间还未开始</h1>"
        '上次签到时间：<font color="#888">2026-10-22 09:11</font>'
    )
    signed_today = next(
        item
        for item in document[0]["rule"]["extract_variables"]
        if item["name"] == "signed_today"
    )
    final_success = document[-1]["rule"]["success_asserts"][0]

    signed_match = rendered_rule_pattern(signed_today["re"]).search(html)
    success_match = rendered_rule_pattern(
        final_success["re"],
        account_uid="42",
    ).search(html)

    assert signed_match is not None, path
    assert signed_match.group(1) == "您今天已经签到过了", path
    assert success_match is not None, path


def test_discuz_formhash_extraction_uses_a_dynamic_page_link():
    _path, document = local_templates()["ali213-daily-signin"]
    extraction = next(
        item
        for item in document[0]["rule"]["extract_variables"]
        if item["name"] == "formhash"
    )
    html = (
        '<a href="member.php?mod=logging&amp;action=logout'
        '&amp;formhash=fixture123">退出</a>'
        '<input type="hidden" name="formhash">'
    )

    match = rendered_rule_pattern(extraction["re"]).search(html)

    assert match is not None
    assert match.group(1) == "fixture123"


def test_ali213_checks_the_fixed_thread_reply_instead_of_retired_task_id():
    path, document = local_templates()["ali213-daily-signin"]
    external_urls = [
        step["request"]["url"]
        for step in document
        if str(step.get("request", {}).get("url") or "").startswith(
            ("http://", "https://")
        )
    ]

    assert len(document) == 6, path
    assert "home.php?mod=task" not in " ".join(external_urls), path
    assert document[3]["request"]["method"] == "POST", path
    assert document[3]["request"]["url"].startswith(
        "https://game.ali213.net/forum.php?mod=post&action=reply&"
    ), path
    assert "formhash={{formhash|urlencode}}" in document[3]["request"]["data"], path

    reply = next(
        item
        for item in document[1]["rule"]["extract_variables"]
        if item["name"] == "needs_reply"
    )
    reply_pattern = rendered_rule_pattern(reply["re"], account_uid="42")
    old_reply = (
        '<a href="space-uid-42.html">fixture-user</a>'
        '<em id="authorposton9001">发表于 2026-10-21 08:00</em>'
        '<form id="fastpostform"></form>'
    )
    replied_today = old_reply.replace("2026-10-21", "2026-10-22")

    old_match = reply_pattern.search(old_reply)
    assert old_match is not None, path
    assert old_match.group(1) == 'id="fastpostform"', path
    assert reply_pattern.search(replied_today) is None, path

    final_success = document[-1]["rule"]["success_asserts"][0]["re"]
    final_pattern = rendered_rule_pattern(final_success, account_uid="42")
    old_reply_page = (
        '<a href="space-uid-42.html">fixture-user</a>'
        '<em id="authorposton9001">发表于 2026-10-21 08:00</em>'
    )
    today_reply_page = old_reply_page.replace("2026-10-21", "2026-10-22")

    assert final_pattern.search(old_reply_page) is None, path
    assert final_pattern.search(today_reply_page) is not None, path


def test_conditional_signin_markers_do_not_require_an_incidental_yes():
    fixtures = {
        "hdsky-daily-signin": (
            '<button id="qiandao">开始签到</button>',
            "qiandao",
        ),
        "hdduck-daily-signin": (
            '<button id="qiandao">开始签到</button>',
            "qiandao",
        ),
        "fnnas-forum-daily-signin": (
            '<a href="plugin.php?id=zqlj_sign&amp;sign=fixture-token">'
            "点击打卡</a>",
            "zqlj_sign",
        ),
    }
    for slug, (html, expected) in fixtures.items():
        path, document = local_templates()[slug]
        extraction = next(
            item
            for item in document[0]["rule"]["extract_variables"]
            if item["name"] == "needs_submit"
        )
        match = rendered_rule_pattern(extraction["re"]).search(html)

        assert match is not None, (slug, path)
        assert match.group(1) == expected, (slug, path)


def test_discuz_login_and_structural_challenge_pages_still_fail_closed():
    fixtures = {
        "hdsky-daily-signin": (
            '<form id="lsform"><input name="username"></form>',
            "<title>Just a moment...</title><div id=\"challenge-form\"></div>",
        ),
        "fnnas-forum-daily-signin": (
            '<form id="lsform"><input name="username"></form>',
            "<title>Attention Required! | Cloudflare</title>",
        ),
        "52pojie-daily-signin": (
            '<form id="lsform"><input name="username"></form>',
            "<title>安全验证</title><div id=\"challenge-form\"></div>",
        ),
        "hdduck-daily-signin": (
            '<form id="lsform"><input name="username"></form>',
            "<title>Just a moment...</title><div id=\"challenge-form\"></div>",
        ),
        "ali213-daily-signin": (
            '<form id="lsform"><input name="username"></form>',
            "<title>Just a moment...</title><div id=\"challenge-form\"></div>",
        ),
    }
    for slug, (login_page, challenge_page) in fixtures.items():
        _path, document = local_templates()[slug]
        patterns = [
            assertion["re"]
            for assertion in document[0]["rule"]["failed_asserts"]
        ]
        assert any(re.search(pattern, login_page, re.S) for pattern in patterns), slug
        assert any(
            re.search(pattern, challenge_page, re.S) for pattern in patterns
        ), slug


def test_smzdm_acquires_a_token_before_signing_in():
    path, document = local_templates()["smzdm-daily-signin"]
    token_step, checkin_step = document[:2]

    assert token_step["request"]["url"] == "https://user-api.smzdm.com/robot/token"
    assert checkin_step["request"]["url"] == "https://user-api.smzdm.com/checkin"
    assert any(
        item.get("name") == "robot_token"
        and item.get("from") == "content"
        and "\"token\"" in item.get("re", "")
        for item in token_step["rule"]["extract_variables"]
    ), path
    assert "robot_token" in checkin_step["request"]["data"], path
    assert "&sk=" in checkin_step["request"]["data"], path
    assert "&token=" in checkin_step["request"]["data"], path


def test_smzdm_renders_the_researched_token_and_checkin_signatures():
    path, document = local_templates()["smzdm-daily-signin"]
    environment = SandboxedEnvironment()
    environment.globals["timestamp"] = lambda _type="int": 1777777777
    environment.globals["urlencode"] = lambda value: quote_plus(
        str(value), safe=""
    )
    environment.filters["md5"] = lambda value: hashlib.md5(
        str(value).encode("utf-8")
    ).hexdigest()
    variables = {"robot_token": "fixture-token+slash/value"}

    token_data = environment.from_string(
        document[0]["request"]["data"]
    ).render(**variables)
    checkin_data = environment.from_string(
        document[1]["request"]["data"]
    ).render(**variables)
    token_query = parse_qs(token_data)
    checkin_query = parse_qs(checkin_data)

    expected_token_sign = hashlib.md5(
        b"f=android&time=1777777777000&v=10.4.1&weixin=1"
        b"&key=apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"
    ).hexdigest().upper()
    sk = (
        "ierkM0OZZbsuBKLoAgQ6OJneLMXBQXmzX+LXkNTuKch8Ui2jGlahuFyWIzBiDq/L"
    )
    expected_checkin_sign = hashlib.md5(
        (
            "f=android&sk="
            + sk
            + "&time=1777777777000&token=fixture-token+slash/value"
            + "&v=10.4.1&weixin=1"
            + "&key=apr1$AwP!wRRT$gJ/q.X24poeBInlUJC"
        ).encode("utf-8")
    ).hexdigest().upper()

    assert token_query["sign"] == [expected_token_sign], path
    assert checkin_query["sign"] == [expected_checkin_sign], path
    assert checkin_query["token"] == ["fixture-token+slash/value"], path
    assert checkin_query["sk"] == [sk], path


def test_smzdm_error_assertions_ignore_zero_but_reject_nonzero_codes():
    _path, document = local_templates()["smzdm-daily-signin"]
    patterns = [
        assertion["re"]
        for step in document[:2]
        for assertion in step["rule"]["failed_asserts"]
        if "error_code" in assertion["re"]
    ]

    assert patterns
    for payload in ('{"error_code":0}', '{"error_code":"0"}'):
        assert not any(re.search(pattern, payload) for pattern in patterns), payload
    for payload in ('{"error_code":11111}', '{"error_code":"11111"}'):
        assert any(re.search(pattern, payload) for pattern in patterns), payload


def test_smzdm_unicode_log_step_uses_the_handler_content_parameter():
    _path, document = local_templates()["smzdm-daily-signin"]
    log_step = document[2]

    assert log_step["request"]["url"].endswith("/unicode")
    assert log_step["request"]["data"].startswith("content=")
    assert "msg=" not in log_step["request"]["data"].split("&", 1)[0]


def test_local_metadata_names_every_official_template():
    metadata = json.loads((LOCAL / "meta.json").read_text(encoding="utf-8"))

    assert OFFICIAL_PUBLIC_SLUGS <= set(metadata)
    assert "lwgod" in metadata
    assert all(metadata[slug].get("name") for slug in OFFICIAL_PUBLIC_SLUGS)
