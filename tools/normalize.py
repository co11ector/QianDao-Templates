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

The published library is Cookie-backed HTTP only. Upstream captures are normalized before
publication: captured Cookie values, hard-coded User-Agent strings, literal credential
headers, request cookie arrays, and response cookie metadata are removed. Every external
HTTP(S) request then receives exactly one ``User-Agent: {{user_agent}}`` header. A captured
site Cookie is scoped to the primary request domain rather than leaked to unrelated helper
hosts. Templates using ``browser://`` or automated challenge-solving services are rejected.
Local templates are held to the same final identity rule and fail the whole sync when they
regress.

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
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlsplit

PUBLISHED_REPOSITORY = "https://raw.githubusercontent.com/co11ector/QianDao-Templates/master"
# Shown as the author of the templates this project writes itself, under local/.
LOCAL_AUTHOR = "co11ector"
# Where the app's 评论 button sends people for a local template with no dedicated issue.
LOCAL_COMMENT_URL = "https://github.com/co11ector/QianDao-Templates/issues/1"

CATEGORY_KEYWORDS = (
    ("pt", ("pt", "torrent", "seed", "leaguehd", "hdsky", "柠檬", "pt站")),
    ("forum", ("forum", "bbs", "discuz", "论坛", "破解", "精易", "saraba", "chiphell")),
    ("video", ("bili", "video", "视频", "音乐", "163", "acfun")),
    ("shop", ("shop", "jd", "taobao", "购物")),
)
DEFAULT_CATEGORY = "signin"
CATEGORY_ORDER = ("pt", "forum", "video", "shop", "signin")
COOKIE_PLACEHOLDER = "{{cookie}}"
USER_AGENT_PLACEHOLDER = "{{user_agent}}"
AUTOMATED_CHALLENGE_URL_MARKERS = ("api://util/dddd/ocr",)
AUTOMATED_CHALLENGE_HOSTS = frozenset(
    (
        "2captcha.com",
        "anti-captcha.com",
        "capmonster.cloud",
        "chaojiying.com",
        "jfbym.com",
        "ttshitu.com",
        "truecaptcha.ai",
        "yescaptcha.com",
    )
)
# A deliberately small public-suffix allow-list covers the country suffixes used by
# the public templates. This keeps credential scope inside one registrable site
# without pulling a network-updated suffix database into the publication workflow.
MULTI_LABEL_PUBLIC_SUFFIXES = frozenset(
    (
        "ac.uk",
        "co.jp",
        "co.kr",
        "co.uk",
        "com.au",
        "com.br",
        "com.cn",
        "com.hk",
        "com.mx",
        "com.sg",
        "com.tw",
        "edu.cn",
        "gov.cn",
        "net.au",
        "net.cn",
        "net.hk",
        "org.au",
        "org.cn",
        "org.hk",
        "org.uk",
    )
)
DEFAULT_GUIDANCE_COMMENT = (
    "使用登录后的完整 Cookie 与同一浏览器的 User-Agent 运行本模板。"
    "若站点要求验证码、滑块或其他人工验证，请先在浏览器完成并重新获取凭据；"
    "模板不会自动绕过验证。"
)
RETIRED_BROWSER_MARKERS = ("browser://", "browser_worker", "browser-worker")
SENSITIVE_HEADER_NAMES = frozenset(
    (
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
        "x-xsrf-token",
        "token",
    )
)
RESPONSE_COOKIE_HEADER_NAMES = frozenset(("set-cookie", "set-cookie2"))
TEMPLATE_EXPRESSION = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)
TEMPLATE_QUOTED_OPAQUE = re.compile(r"""['"]([A-Za-z0-9._~+/=-]{16,})['"]""")
OPAQUE_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]{12,}")
LITERAL_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:^|[^a-z0-9_])"
    r"(?:api[_-]?key|api[_-]?secret|client[_-]?secret|access[_-]?token|"
    r"refresh[_-]?token|password|passwd|pwd|secret|token)"
    r"\s*[:=]\s*[\"']?([A-Za-z0-9._~+/=-]{16,})[\"']?"
)
LITERAL_AUTHORIZATION = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization)\s*[:=]\s*"
    r"(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"
)
URL_USERINFO = re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@")
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


def _header_name(header: dict) -> str:
    return str(header.get("name") or "").strip().casefold()


def _header_value(header: dict) -> str:
    return str(header.get("value") or "")


def _templated_secret_value_is_safe(value: str) -> bool:
    """Allow runtime-derived credentials without allowing captured literal values."""
    if not TEMPLATE_EXPRESSION.search(value):
        return False
    if TEMPLATE_QUOTED_OPAQUE.search(value):
        return False
    literal = TEMPLATE_EXPRESSION.sub("", value)
    # Prefixes such as ``Bearer `` and ``Basic `` remain after removing the template.
    # A long opaque remainder is likely a captured credential beside a placeholder.
    return OPAQUE_TOKEN.search(literal) is None


def _request_secret_violation(request: dict) -> str | None:
    """Reject high-confidence literal credentials outside the known header fields."""
    values = [str(request.get("url") or ""), str(request.get("data") or "")]
    headers = request.get("headers")
    if isinstance(headers, list):
        for header in headers:
            if isinstance(header, dict):
                values.append(_header_value(header))
    for value in values:
        if URL_USERINFO.search(value):
            return "request URLs must not contain embedded credentials"
        if LITERAL_AUTHORIZATION.search(value):
            return "literal authorization values must not be published"
        if LITERAL_SECRET_ASSIGNMENT.search(value):
            return "literal request credentials must not be published"
    return None


def _requests(document):
    if not isinstance(document, list):
        return
    for step in document:
        if not isinstance(step, dict):
            continue
        request = step.get("request")
        if not isinstance(request, dict):
            continue
        yield step, request


def _is_external_request(request: dict) -> bool:
    return str(request.get("url") or "").startswith(("http://", "https://"))


def _request_host(url: str) -> str | None:
    try:
        host = urlsplit(str(url or "")).hostname
    except ValueError:
        return None
    return host.rstrip(".").casefold() if host else None


def _credential_scope(host: str | None) -> str | None:
    """Return the narrowest stable site scope used for the Cookie placeholder."""

    if not host:
        return None
    host = host.rstrip(".").casefold()
    if "{{" in host or "{%" in host or host == "localhost":
        return host
    try:
        import ipaddress

        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    suffix = ".".join(labels[-2:])
    if suffix in MULTI_LABEL_PUBLIC_SUFFIXES:
        return ".".join(labels[-3:])
    return suffix


def _document_cookie_scope(document) -> str | None:
    scopes = []
    for _step, request in _requests(document):
        if not _is_external_request(request):
            continue
        scope = _credential_scope(
            _request_host(str(request.get("url") or ""))
        )
        if scope:
            scopes.append(scope)
    if not scopes:
        return None
    counts = Counter(scopes)
    return max(counts, key=lambda scope: (counts[scope], -scopes.index(scope)))


def _request_uses_site_cookie(request: dict, cookie_scope: str | None) -> bool:
    if not _is_external_request(request):
        return False
    request_scope = _credential_scope(
        _request_host(str(request.get("url") or ""))
    )
    return request_scope is not None and request_scope == cookie_scope


def automated_challenge_violation(document) -> str | None:
    """Reject templates that actively solve or bypass a human challenge."""

    for _step, request in _requests(document):
        url = str(request.get("url") or "").strip()
        lowered_url = url.casefold()
        if any(marker in lowered_url for marker in AUTOMATED_CHALLENGE_URL_MARKERS):
            return "automated CAPTCHA solving is not permitted"
        host = _request_host(url)
        if host and any(
            host == blocked or host.endswith(f".{blocked}")
            for blocked in AUTOMATED_CHALLENGE_HOSTS
        ):
            return "third-party CAPTCHA solving services are not permitted"
    return None


def apply_template_guidance(
    document, record_comment="", *, require_record_comment=True
):
    """Ensure the editor and template list both carry operator guidance."""
    record_comment = str(record_comment or "").strip()
    first_step = None
    document_comment = ""
    for step in document:
        if not isinstance(step, dict):
            continue
        request = step.get("request")
        if not isinstance(request, dict):
            continue
        if first_step is None:
            first_step = step
        comment = str(step.get("comment") or "").strip()
        if comment:
            document_comment = comment
            break

    guidance = record_comment or document_comment or DEFAULT_GUIDANCE_COMMENT
    changed = not document_comment
    if require_record_comment and not record_comment:
        changed = True
    if first_step is not None and not str(first_step.get("comment") or "").strip():
        first_step["comment"] = guidance
        changed = True
    return guidance, changed


def normalise_upstream_document(document):
    """Return a sanitized Cookie-backed document and a count of removed fields."""
    changes = {
        "cookie_headers": 0,
        "user_agent_headers": 0,
        "sensitive_headers": 0,
        "request_cookies": 0,
        "response_cookies": 0,
    }
    if not isinstance(document, list) or not document:
        return None, "not a non-empty JSON array", changes

    encoded = json.dumps(document, ensure_ascii=False).casefold()
    if any(marker in encoded for marker in RETIRED_BROWSER_MARKERS):
        return None, "browser execution is retired", changes
    violation = automated_challenge_violation(document)
    if violation is not None:
        return None, violation, changes

    external_requests = 0
    cookie_scope = _document_cookie_scope(document)
    for step, request in _requests(document):
        is_external = _is_external_request(request)
        sends_site_cookie = _request_uses_site_cookie(request, cookie_scope)
        if is_external:
            external_requests += 1
        headers = request.get("headers")
        if not isinstance(headers, list):
            headers = []
        sanitized_headers = []
        for header in headers:
            if not isinstance(header, dict):
                continue
            name = _header_name(header)
            value = _header_value(header)
            if name == "cookie":
                if value != COOKIE_PLACEHOLDER:
                    changes["cookie_headers"] += 1
                continue
            if name == "user-agent":
                if value != USER_AGENT_PLACEHOLDER:
                    changes["user_agent_headers"] += 1
                continue
            if name in SENSITIVE_HEADER_NAMES and not _templated_secret_value_is_safe(
                value
            ):
                changes["sensitive_headers"] += 1
                continue
            sanitized_headers.append(header)
        request["headers"] = (
            [
                *(
                    [{"name": "Cookie", "value": COOKIE_PLACEHOLDER}]
                    if sends_site_cookie
                    else []
                ),
                {"name": "User-Agent", "value": USER_AGENT_PLACEHOLDER},
                *sanitized_headers,
            ]
            if is_external
            else sanitized_headers
        )
        if request.pop("cookies", None):
            changes["request_cookies"] += 1

        response = step.get("response")
        if not isinstance(response, dict):
            continue
        response_headers = response.get("headers")
        if isinstance(response_headers, list):
            kept = []
            for header in response_headers:
                if not isinstance(header, dict):
                    continue
                name = _header_name(header)
                if (
                    name in RESPONSE_COOKIE_HEADER_NAMES
                    or name in SENSITIVE_HEADER_NAMES
                ):
                    changes["sensitive_headers"] += 1
                    continue
                kept.append(header)
            response["headers"] = kept
        if response.pop("cookies", None):
            changes["response_cookies"] += 1

    if not external_requests:
        return None, "no external HTTP(S) request", changes
    violation = cookie_only_violation(document)
    if violation is not None:
        return None, violation, changes
    return document, None, changes


def cookie_only_violation(document) -> str | None:
    """Return why a HAR document is not safe for the Cookie-only library."""
    if not isinstance(document, list) or not document:
        return "not a non-empty JSON array"

    encoded = json.dumps(document, ensure_ascii=False).casefold()
    if any(marker in encoded for marker in RETIRED_BROWSER_MARKERS):
        return "browser execution is retired"
    challenge_violation = automated_challenge_violation(document)
    if challenge_violation is not None:
        return challenge_violation

    external_requests = 0
    cookie_scope = _document_cookie_scope(document)
    for step in document:
        if not isinstance(step, dict):
            continue
        request = step.get("request")
        if not isinstance(request, dict):
            continue
        url = str(request.get("url") or "")
        is_external = url.startswith(("http://", "https://"))
        if is_external:
            external_requests += 1
        headers = request.get("headers")
        if not isinstance(headers, list):
            headers = []
        cookie_values = []
        user_agent_values = []
        for header in headers:
            if not isinstance(header, dict):
                continue
            name = str(header.get("name") or "").strip().casefold()
            value = str(header.get("value") or "")
            if name == "cookie":
                cookie_values.append(value)
            elif name == "user-agent":
                user_agent_values.append(value)
            elif name in SENSITIVE_HEADER_NAMES and not _templated_secret_value_is_safe(
                value
            ):
                return "request credential header values must be templated"
        if is_external:
            if user_agent_values != [USER_AGENT_PLACEHOLDER]:
                return (
                    "every external request must use exactly one "
                    "User-Agent: {{user_agent}}"
                )
            if _request_uses_site_cookie(request, cookie_scope):
                if cookie_values != [COOKIE_PLACEHOLDER]:
                    return (
                        "same-site requests must use exactly one "
                        "Cookie: {{cookie}}"
                    )
            elif cookie_values:
                return "third-party requests must not carry the site Cookie"
        elif any(value != COOKIE_PLACEHOLDER for value in cookie_values):
            return "internal request Cookie values must not be published"
        elif any(value != USER_AGENT_PLACEHOLDER for value in user_agent_values):
            return "internal request User-Agent values must not be published"
        secret_violation = _request_secret_violation(request)
        if secret_violation is not None:
            return secret_violation
        response = step.get("response")
        if isinstance(response, dict):
            for header in response.get("headers") or []:
                if not isinstance(header, dict):
                    continue
                if _header_name(header) in (
                    RESPONSE_COOKIE_HEADER_NAMES | SENSITIVE_HEADER_NAMES
                ):
                    return "response credential headers must not be published"
            response_cookies = response.get("cookies")
            if isinstance(response_cookies, list):
                for cookie in response_cookies:
                    if isinstance(cookie, dict) and not _templated_secret_value_is_safe(
                        _header_value(cookie)
                    ):
                        return "response cookie values must be templated"
        request_cookies = request.get("cookies")
        if isinstance(request_cookies, list):
            for cookie in request_cookies:
                if isinstance(cookie, dict) and not _templated_secret_value_is_safe(
                    _header_value(cookie)
                ):
                    return "request cookie values must be templated"

    if not external_requests:
        return "no external HTTP(S) request"
    return None


def categorise(name: str, url: str, author: str) -> str:
    haystack = " ".join(str(part or "") for part in (name, url, author)).lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


def local_root_default() -> Path:
    """The repository's own hand-maintained templates: <repo>/local/<category>/*.har."""
    return Path(__file__).resolve().parent.parent / "local"


def _git_commit_timestamp(path: Path):
    """Return the file's last commit time as a timezone-independent UTC datetime."""
    try:
        completed = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", path.name],
            cwd=str(path.parent),
            capture_output=True,
            text=True,
            check=False,
        )
        raw = completed.stdout.strip()
        if completed.returncode == 0 and raw:
            return datetime.datetime.fromtimestamp(
                int(raw), tz=datetime.timezone.utc
            )
    except (OSError, OverflowError, ValueError):
        pass
    return None


def _file_mtime_timestamp(path: Path) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(
        path.stat().st_mtime, tz=datetime.timezone.utc
    )


def _canonical_har_bytes(path: Path) -> bytes:
    """Read a validated HAR with universal newlines and encode deterministic UTF-8."""
    return path.read_text(encoding="utf-8").encode("utf-8")


def local_record_metadata(path: Path, comment_url: str, meta_path: Path = None) -> dict:
    """The version/date/update/commenturl fields the application expects on a record.

    version must be an int-comparable date because the app decides whether to re-import
    with `int(current["version"]) < int(template["version"])`, and a record without it
    raises and aborts the whole refresh for every user. Git's last commit epoch for the
    file keeps the value stable across checkouts and time zones - the file mtime does not,
    and the daily workflow would then emit a new index every run - while still moving
    forward whenever the template is actually edited. Outside a work tree it falls back
    to the mtime, interpreted as UTC.

    commenturl is where the app's 评论 button sends people. Every upstream record points
    at the issue where that template was discussed, so ours points at this project's
    request board; pointing it at the template file made the button dump raw JSON.
    """
    stamp = _git_commit_timestamp(path)
    if stamp is None:
        stamp = _file_mtime_timestamp(path)
    # A metadata-only change (display name, discussion link) has to move the version too,
    # or the app compares equal to what it already stored and skips the row until someone
    # presses 重建缓存 - which is exactly the trap the day-granularity version set.
    if meta_path is not None and Path(meta_path).is_file():
        meta_stamp = _file_mtime_timestamp(Path(meta_path))
        committed_meta_stamp = _git_commit_timestamp(Path(meta_path))
        if committed_meta_stamp is not None:
            meta_stamp = committed_meta_stamp
        stamp = max(stamp, meta_stamp)
    return {
        "version": stamp.strftime("%Y%m%d%H%M"),
        "date": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "update": int(stamp.timestamp()),
        "commenturl": comment_url,
    }


def read_local_metadata(local_root: Path) -> dict:
    """Per-template metadata from local/meta.json: the display name and the discussion link.

    Upstream gives every template its own 「评论区」 issue and the app's 评论 button opens
    it, so ours are mapped the same way. The display name can differ from the file name,
    which stays ASCII and stable because the app's identity is (name, repo, url, branch).
    Anything unmapped falls back to the request board, which is still somewhere a reader
    can actually leave a comment.
    """
    path = Path(local_root) / "meta.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}

    result = {}
    for name, value in data.items():
        if isinstance(value, str) and value.startswith("http"):
            result[str(name)] = {"name": None, "commenturl": value}
        elif isinstance(value, dict):
            comment_url = str(value.get("commenturl") or "")
            result[str(name)] = {
                "name": str(value["name"]) if value.get("name") else None,
                "commenturl": comment_url if comment_url.startswith("http") else None,
            }
    return result


def read_retired_local_entries(local_root: Path) -> set:
    """Names or filename stems this project has deliberately retired.

    The public repository still mirrors the upstream index, and an older
    project-owned template can therefore survive in that index after its
    source has been removed from local/. A small explicit retirement list
    keeps those entries out of both the copied tree and the published index.
    """
    path = Path(local_root) / "retired.json"
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {
        str(value).strip().casefold()
        for value in data
        if isinstance(value, str) and str(value).strip()
    }


def is_retired(record: dict, retired_entries: set) -> bool:
    filename = str(record.get("filename") or "")
    candidates = {
        str(record.get("name") or "").casefold(),
        Path(filename).stem.casefold(),
    }
    return bool(candidates & retired_entries)


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


def dedupe_by_filename(stored_by_name):
    """Keep one record per published filename, the newest version.

    The application matches a subscription on "<filename>|<reponame>", so two records for one
    filename mean two library rows and a duplicate entry in the public list - and the older one
    can never be displaced, because the index keeps offering it. Returns the collapsed mapping
    and the names that were dropped.
    """
    best = {}
    dropped = []
    for name, record in stored_by_name.items():
        filename = record.get("filename") or ""
        current = best.get(filename)
        if current is None or str(record.get("version") or "") > str(current[1].get("version") or ""):
            if current is not None:
                dropped.append(current[0])
            best[filename] = (name, record)
        else:
            dropped.append(name)
    return {name: record for name, record in best.values()}, dropped


def _canonical_document_bytes(document) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def validate_published_tree(root: Path, minimum_templates: int = 0) -> dict:
    """Validate the generated public tree without trusting its index or embedded bodies."""
    root = Path(root)
    index = json.loads((root / "tpls_history.json").read_text(encoding="utf-8"))
    records = index.get("har") or {}
    records = list(records.values()) if isinstance(records, dict) else list(records)
    if len(records) < minimum_templates:
        raise ValueError(
            "published template count %d is below the required minimum %d"
            % (len(records), minimum_templates)
        )

    seen = set()
    indexed_files = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("published index contains a non-object template record")
        filename = str(record.get("filename") or "")
        if not filename:
            raise ValueError("published index contains a record without a filename")
        if filename in seen:
            raise ValueError("published index contains duplicate filename %s" % filename)
        seen.add(filename)
        indexed_files.add(filename)
        path = root / filename
        if not path.is_file():
            raise ValueError("published index points at missing file %s" % filename)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("published template is unreadable: %s" % filename) from error
        violation = cookie_only_violation(document)
        if violation is not None:
            raise ValueError("%s violates the Cookie-only policy: %s" % (filename, violation))
        record_comment = str(record.get("comments") or "").strip()
        document_comment = ""
        for step in document:
            if not isinstance(step, dict):
                continue
            document_comment = str(step.get("comment") or "").strip()
            if document_comment:
                break
        if not record_comment or not document_comment:
            raise ValueError(
                "%s is missing a public instruction header" % filename
            )
        try:
            embedded = base64.b64decode(str(record.get("content") or ""), validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("published record has invalid embedded content: %s" % filename) from error
        if embedded != path.read_bytes():
            raise ValueError("published record content does not match %s" % filename)

    actual_files = {
        path.relative_to(root).as_posix()
        for path in (root / "templates").rglob("*.har")
    }
    if actual_files != indexed_files:
        missing = sorted(indexed_files - actual_files)
        orphaned = sorted(actual_files - indexed_files)
        raise ValueError(
            "published tree/index mismatch (missing=%s, orphaned=%s)"
            % (missing[:5], orphaned[:5])
        )
    return {"templates": len(records), "files": len(actual_files)}


def normalise(source: Path, target: Path, local_root=None) -> dict:
    report = {
        "moved": 0,
        "local": 0,
        "skipped": [],
        "overridden": [],
        "retired": [],
        "pruned": [],
        "rejected_cookie_only": [],
        "guidance_added": 0,
        "transformed": 0,
        "removed": {
            "cookie_headers": 0,
            "user_agent_headers": 0,
            "sensitive_headers": 0,
            "request_cookies": 0,
            "response_cookies": 0,
        },
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
    resolved_local_root = (
        local_root_default() if local_root is None else Path(local_root)
    )
    retired_entries = read_retired_local_entries(resolved_local_root)

    for record, category in read_har_entries(source):
        filename = record.get("filename") or ""
        if is_retired(record, retired_entries):
            report["retired"].append(record.get("name") or filename)
            continue
        source_file = source / filename
        if not source_file.is_file():
            source_file = source / filename.lstrip("/")
        if not source_file.is_file():
            report["skipped"].append("%s: missing" % filename)
            continue
        try:
            document = json.loads(source_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            report["skipped"].append(
                "%s: unreadable (%s)" % (filename, error.__class__.__name__)
            )
            continue
        document, violation, changes = normalise_upstream_document(document)
        if violation is not None:
            if violation == "no external HTTP(S) request":
                report["skipped"].append("%s: %s" % (filename, violation))
                continue
            report["rejected_cookie_only"].append(
                "%s: %s" % (filename, violation)
            )
            continue
        if any(changes.values()):
            report["transformed"] += 1
        for key, count in changes.items():
            report["removed"][key] += count
        guidance, guidance_changed = apply_template_guidance(
            document, record.get("comments")
        )
        if guidance_changed:
            report["guidance_added"] += 1

        relative = "templates/%s/%s" % (category, source_file.name)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        transformed_bytes = _canonical_document_bytes(document)
        destination.write_bytes(transformed_bytes)

        stored = dict(record)
        stored["filename"] = relative
        stored["comments"] = guidance
        # The record kept the upstream raw URL, which pointed at the repository root.
        # Ours lives under the category, and non-ASCII names have to be quoted, so the
        # stored url is rebuilt from the published path rather than the bare filename.
        stored["url"] = "%s/%s" % (PUBLISHED_REPOSITORY, quote(relative))
        # The app prefers embedded content when present. Re-embed the HAR we validated so
        # a stale browser or legacy body in upstream metadata cannot bypass the published
        # file's Cookie-only gate. Universal-newline reading plus UTF-8 encoding prevents
        # Windows CRLF checkout bytes from changing the generated index on GitHub Actions.
        stored["content"] = base64.b64encode(transformed_bytes).decode("ascii")
        stored_by_name[record.get("name") or source_file.name] = stored
        report["moved"] += 1
        report["categories"].setdefault(category, 0)
        report["categories"][category] += 1

    # Merge the templates this project maintains itself. They are copied verbatim and
    # indexed like the upstream ones, except that the category comes from the directory
    # rather than from keyword matching, and a local name wins over an upstream one.
    local_metadata = read_local_metadata(resolved_local_root)
    for path, category in read_local_entries(resolved_local_root):
        if path.stem.casefold() in retired_entries:
            report["retired"].append(path.stem)
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            report["skipped"].append(
                "local/%s/%s: unreadable (%s)"
                % (category, path.name, error.__class__.__name__)
            )
            continue
        violation = cookie_only_violation(document)
        if violation is not None:
            raise ValueError(
                "local/%s/%s violates the Cookie-only policy: %s"
                % (category, path.name, violation)
            )

        comment, guidance_changed = apply_template_guidance(
            document, require_record_comment=False
        )
        if guidance_changed:
            report["guidance_added"] += 1

        entry = local_metadata.get(path.stem) or {}
        name = entry.get("name") or path.stem
        comment_url = entry.get("commenturl") or LOCAL_COMMENT_URL
        relative = "templates/%s/%s" % (category, path.name)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        local_bytes = (
            _canonical_document_bytes(document)
            if guidance_changed
            else _canonical_har_bytes(path)
        )
        destination.write_bytes(local_bytes)

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
            "content": base64.b64encode(local_bytes).decode("ascii"),
            **local_record_metadata(
                path, comment_url, resolved_local_root / "meta.json"
            ),
        }
        report["local"] += 1
        report["local_templates"].append((name, relative))
        report["categories"].setdefault(category, 0)
        report["categories"][category] += 1

    stored_by_name, dropped = dedupe_by_filename(stored_by_name)
    report["deduped"] = dropped

    published_filenames = {
        record.get("filename") for record in stored_by_name.values()
    }
    for path in sorted((target / "templates").rglob("*.har")):
        relative = path.relative_to(target).as_posix()
        if relative not in published_filenames:
            path.unlink()
            report["pruned"].append(relative)

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
        '  <img alt="QianDao Templates" src="brand/qiandao-templates-avatar-light.png" width="180">',
        '</picture>',
        '</p>',
        "",
        '<h1 align="center">QianDao Templates</h1>',
        '<p align="center"><strong>QianDao 官方精选公共模板仓库</strong> · 社区签到模板每日自动同步与分类整理</p>',
        "",
        '<p align="center">',
        '  <a href="https://github.com/co11ector/QianDao-Templates/actions/workflows/sync-upstream.yml"><img src="https://github.com/co11ector/QianDao-Templates/actions/workflows/sync-upstream.yml/badge.svg" alt="Sync Upstream Status"></a>',
        '  <img src="https://img.shields.io/badge/Format-HAR%20Blueprint-0284c7?logo=json" alt="HAR Blueprint">',
        '  <img src="https://img.shields.io/badge/Auto%20Sync-Daily%2003%3A17%20UTC-2563eb?logo=githubactions" alt="Auto Sync">',
        '  <img src="https://img.shields.io/badge/License-MIT-059669" alt="License">',
        '</p>',
        "",
        "> 「QianDao 自动化运行台」**官方精选公共模板仓库**：持续从上游社区仓库 [`qd-today/templates`](https://github.com/qd-today/templates) 每日自动同步、校验并按站点类型分类归纳，供 [QianDao](https://github.com/co11ector/QianDao) 用户开箱即用、一键订阅与定时签到。",
        "",
        "### 🌟 核心特性",
        "",
        "- ⚡ **开箱可用**：订阅本仓库即可在应用内挑选模板，不必自己收集；",
        "- 🔄 **每日更新**：每天自动比对上游社区变动，24 小时内全自动跟进同步；",
        "- 📂 **整理清楚**：按站点类型分目录，索引与文件一一对应；",
        "- 🛡️ **来源可查**：每个模板的作者与出处都保留在索引里。",
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
        "3. 自动清理抓包里的 Cookie、硬编码 UA、静态凭据 Header 与 Cookie 元数据，"
        "并拒绝请求 URL/请求体中的字面凭据；",
        "4. 为每个外部 HTTP(S) 请求补齐一份 `User-Agent: {{user_agent}}`；"
        "`Cookie: {{cookie}}` 只注入同一站点范围，第三方辅助请求不带站点 Cookie；",
        "5. 拒绝 `browser://`、第三方打码服务和内置 OCR 验证码绕过；",
        "6. 发布前硬门禁要求至少 375 个模板，且索引内容必须与 HAR 文件逐字一致；",
        "7. 重新生成 README 与 CATEGORIES，有变化才提交推送。",
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
    if len(argv) in (3, 4) and argv[1] == "--validate":
        minimum = int(argv[3]) if len(argv) == 4 else 0
        try:
            report = validate_published_tree(Path(argv[2]), minimum)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print("published tree validation failed: %s" % error)
            return 1
        print(
            "validated %d Cookie-only templates (%d files)"
            % (report["templates"], report["files"])
        )
        return 0
    if len(argv) != 3:
        print("usage: normalize.py <source> <target>")
        print("       normalize.py --validate <published-root> [minimum]")
        return 2
    report = normalise(Path(argv[1]), Path(argv[2]))
    print("moved %d (%d local)" % (report["moved"], report["local"]))
    print("transformed upstream %d" % report["transformed"])
    print(
        "removed cookie=%d user-agent=%d sensitive=%d request-cookies=%d "
        "response-cookies=%d"
        % (
            report["removed"]["cookie_headers"],
            report["removed"]["user_agent_headers"],
            report["removed"]["sensitive_headers"],
            report["removed"]["request_cookies"],
            report["removed"]["response_cookies"],
        )
    )
    for name, relative in report["local_templates"]:
        print("  local %s -> %s" % (name, relative))
    for name in report["overridden"]:
        print("  local override %s" % name)
    for name in report["retired"]:
        print("  retired %s" % name)
    for name in report["pruned"]:
        print("  pruned %s" % name)
    for rejected in report["rejected_cookie_only"]:
        print("  rejected Cookie-only %s" % rejected)
    for category in CATEGORY_ORDER:
        if report["categories"].get(category):
            print("  %-8s %d" % (category, report["categories"][category]))
    for skipped in report["skipped"]:
        print("  skipped %s" % skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
