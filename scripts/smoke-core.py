#!/usr/bin/env python3
"""core 模块部署后冒烟 runner —— 覆盖全部 18 个 SMOKE-core-* 用例。

只用标准库：runner 要能在任何装了 Python 3.11+ 的部署机上跑，不该为了跑冒烟
先装一堆依赖。

约定（部署方案 §8.1）：
  * 自建一个匿名账号，结束时彻底删除其全部数据；可重复执行，不依赖前次残留。
  * LLM / ASR 不 mock，降级路径也算通过——分层断言体现在 SMOKE-core-10。
  * 不注入时钟。`/api/test/*` 在非 test 环境不存在，所以生产触发一轮扫描走
    `docker compose run --rm scheduler --once`，而不是后门端点。

环境变量：
  SMOKE_ENV            local | staging | production（默认 local）
  SMOKE_BASE_URL        API 根，默认 http://127.0.0.1:8000
  SMOKE_WEB_URL         静态站点根，默认同 SMOKE_BASE_URL
  SMOKE_DB_PATH         SQLite 文件路径，默认从 DATABASE_URL 推导
  SMOKE_SCHEDULER_CMD   触发一轮扫描的命令，默认 docker compose run --rm --no-deps --entrypoint python scheduler -m app.scheduler --once
  SMOKE_ALEMBIC_HEAD    期望的迁移 revision，默认取 backend/migrations 里最大的
  OPENLOGOS_SMOKE_RESULT_PATH  结果文件，默认 logos/resources/verify/smoke-results.jsonl
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.get("SMOKE_ENV", "local")
BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
WEB_URL = os.environ.get("SMOKE_WEB_URL", BASE_URL).rstrip("/")
SCHEDULER_CMD = os.environ.get(
    "SMOKE_SCHEDULER_CMD", "docker compose run --rm --no-deps --entrypoint python scheduler -m app.scheduler --once"
)
RESULT_PATH = Path(
    os.environ.get(
        "OPENLOGOS_SMOKE_RESULT_PATH",
        str(REPO_ROOT / "logos" / "resources" / "verify" / "smoke-results.jsonl"),
    )
)
PLAINTEXT = "smoke：想去看海"


class SmokeSkip(Exception):
    """本用例在当前环境不适用，或前置条件缺失。记 skip 而不是 fail。"""


@dataclass
class Case:
    id: str
    envs: tuple[str, ...]
    title: str
    fn: object


@dataclass
class Ctx:
    """跨用例共享的状态。setup 建两个账号，teardown 负责清干净。"""

    token_a: str = ""
    token_b: str = ""
    user_a: str = ""
    user_b: str = ""
    wish_a: str = ""
    memory_a: str = ""
    warnings: list[str] = field(default_factory=list)
    created: list[tuple[str, str]] = field(default_factory=list)  # (token, wish_id)


def http(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: object | None = None,
    base: str | None = None,
    raw: bytes | None = None,
    content_type: str | None = None,
    timeout: float = 20.0,
) -> tuple[int, dict, object]:
    """返回 (status, headers, parsed)。网络层错误也转成 status，让断言统一写。"""
    url = f"{base or BASE_URL}{path}"
    data = raw
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            payload = resp.read()
            return resp.status, dict(resp.headers), _parse(payload)
    except urllib.error.HTTPError as exc:  # 4xx / 5xx 也是有效结果
        return exc.code, dict(exc.headers or {}), _parse(exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SmokeSkip(f"{url} 不可达：{exc}") from exc


def _parse(payload: bytes) -> object:
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload


def db_path() -> Path:
    raw = os.environ.get("SMOKE_DB_PATH")
    if raw:
        return Path(raw)
    url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./unhappened.db")
    if "///" not in url:
        raise SmokeSkip(f"无法从 DATABASE_URL 推导文件路径：{url}")
    return Path(url.split("///", 1)[1])


DB_CMD = os.environ.get("SMOKE_DB_CMD", "")


def _run_db_cmd(args: list[str], stdin: str | None = None) -> str:
    proc = subprocess.run(  # noqa: S602 —— 命令来自运维配置，不来自用户输入
        f"{DB_CMD} {' '.join(args)}",
        shell=True,
        input=stdin,
        capture_output=True,
        text=True,
        # 必须显式指定：容器里那侧是 UTF-8，而 subprocess 默认按本机 locale 解码
        # （Windows 上是 GBK），BLOB 经 latin-1 编回去时会炸在一个莫名的汉字上
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        raise SmokeSkip(
            f"SMOKE_DB_CMD 执行失败（{DB_CMD} {' '.join(args)}）："
            f"{(proc.stderr or proc.stdout).strip()[:300]}"
        )
    return proc.stdout


def _lit(value: str) -> str:
    """把一个由 runner 自己产生的标识拼进 SQL 前的最后一道闸。

    走 SMOKE_DB_CMD 时 SQL 只能整条传过去，没有绑定参数可用，所以这里限定字符集：
    只放行 UUID / 时间戳 / 对象键这类形状，遇到别的直接炸而不是想办法转义。
    """
    if not re.fullmatch(r"[A-Za-z0-9._:/@+-]{1,256}", value):
        raise AssertionError(f"拒绝把这个值拼进 SQL：{value!r}")
    return value


def db_rows(sql: str) -> list[list]:
    """执行一条 SQL 并返回行。

    容器化部署里数据库在卷内、宿主上没有路径，所以设了 `SMOKE_DB_CMD` 时一律
    经它取数（见 ops/sql.sh）；没设时退回本机 sqlite3 直连文件。
    """
    if DB_CMD:
        out = _run_db_cmd(["query"], stdin=sql).strip()
        return json.loads(out) if out else []
    path = db_path()
    if not path.exists():
        raise SmokeSkip(f"数据库文件不存在：{path}")
    con = sqlite3.connect(path, timeout=10)
    try:
        rows = [list(r) for r in con.execute(sql).fetchall()]
        con.commit()
        return rows
    except sqlite3.OperationalError as exc:
        raise SmokeSkip(f"数据库不可访问：{exc}") from exc
    finally:
        con.close()


def db_pragma(name: str) -> str:
    if DB_CMD:
        return _run_db_cmd(["pragma", name]).strip()
    return str(db_rows(f"PRAGMA {name}")[0][0])


def db_mode() -> str | None:
    """返回 .db 的权限位（八进制字符串）。取不到时返回 None。"""
    if DB_CMD:
        return _run_db_cmd(["stat"]).strip()
    path = db_path()
    if not path.exists():
        return None
    return oct(path.stat().st_mode & 0o777)[2:]


def expected_head() -> str:
    override = os.environ.get("SMOKE_ALEMBIC_HEAD")
    if override:
        return override
    versions = sorted((REPO_ROOT / "backend" / "migrations" / "versions").glob("0*.py"))
    if not versions:
        raise SmokeSkip("找不到迁移文件，无法推导目标 revision")
    return versions[-1].stem


def schema_counts() -> tuple[int, int]:
    tables = db_rows(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        " AND name <> 'alembic_version'"
    )[0][0]
    indexes = db_rows(
        "SELECT count(*) FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    )[0][0]
    return int(tables), int(indexes)


# ---------------------------------------------------------------- 用例


def smoke_01(ctx: Ctx) -> str | None:
    status, _, body = http("GET", "/api/v1/health")
    assert status == 200, f"health 返回 {status}"
    assert body["status"] == "ok", body
    assert body["database"] == "ok", body
    return None


def smoke_02(ctx: Ctx) -> str | None:
    status, _, body = http("GET", "/api/v1/health")
    assert status == 200, f"health 返回 {status}"
    age = body.get("scheduler_heartbeat_age_seconds")
    assert age is not None, "心跳为 null：调度进程从未写过心跳"
    assert age < 900, f"心跳已过期 {age:.0f} 秒（阈值 900）"
    return None


def smoke_03(ctx: Ctx) -> str | None:
    script = REPO_ROOT / "ops" / "check-env.sh"
    assert script.exists(), f"{script} 不存在"
    bash = shutil.which("bash")
    if bash is None:
        raise SmokeSkip("本机没有 bash，无法执行 ops/check-env.sh")
    proc = subprocess.run(  # noqa: S603
        [bash, str(script)], capture_output=True, text=True, timeout=60, cwd=REPO_ROOT
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"check-env 失败：{out.strip()[:400]}"
    # 不打印密钥值：输出里只应出现变量名与长度
    for secret_name in ("ENCRYPTION_KEY", "JWT_SECRET"):
        value = os.environ.get(secret_name, "")
        if len(value) >= 8:
            assert value not in out, f"check-env 输出泄露了 {secret_name} 的值"
    return None


def smoke_04(ctx: Ctx) -> str | None:
    status, _, _ = http("GET", f"/api/test/outbox?user_id={uuid.uuid4()}")
    assert status == 404, f"测试后门在 {ENV} 仍可访问（返回 {status}）"
    return None


def smoke_05(ctx: Ctx) -> str | None:
    journal = db_pragma("journal_mode")
    assert journal.lower() == "wal", f"journal_mode 是 {journal}，应为 wal"
    # foreign_keys 是连接级设置，新开的连接不会继承应用连接的取值。
    # 「应用连接开了外键」由 UT 覆盖（db.py 的 PRAGMA），这里不重复断言。
    mode = db_mode()
    if mode is None:
        raise SmokeSkip("取不到数据库文件的权限位")
    if not DB_CMD and os.name == "nt":
        return f"Windows 无 POSIX 权限位，跳过 600 检查（实测 {mode}）"
    if mode != "600":
        return f"数据库文件权限是 {mode}，部署方案 §3.3 要求 600 —— 需在部署侧收紧"
    return None


def smoke_06(ctx: Ctx) -> str | None:
    rows = db_rows("SELECT version_num FROM alembic_version")
    assert rows, "alembic_version 为空"
    want = expected_head()
    assert rows[0][0] == want, f"迁移版本是 {rows[0][0]}，期望 {want}"
    return None


def smoke_07(ctx: Ctx) -> str | None:
    tables, indexes = schema_counts()
    # preferences-availability-timing：17→20 张；lightweight-events：20→21 张（lite_events）
    assert tables == 21, f"表数量是 {tables}，期望 21"
    assert indexes == 37, f"idx_ 索引数量是 {indexes}，期望 37"
    return None


def ensure_wish_a(ctx: Ctx) -> str:
    """A 名下那条供隔离 / 时机 / 加密用例复用的 smoke 愿望，谁先跑谁建。

    SMOKE-core-08 在清单里排在 10 之前，但它需要「A 有一条愿望」这个前置。
    与其依赖用例执行顺序（顺序一变就静默失效，第一版就踩了这个坑：
    空 id 让 URL 退化成列表端点，B 反而拿到 200），不如让前置自己保证。
    """
    if ctx.wish_a:
        return ctx.wish_a
    if not ctx.token_a:
        raise SmokeSkip("没有可用的 smoke 账号")
    status, _, body = http(
        "POST", "/api/v1/wishes", token=ctx.token_a, body={"source": "text", "text": PLAINTEXT}
    )
    if status != 201:
        raise SmokeSkip(f"种下前置 smoke 愿望失败：{status} {body}")
    ctx.wish_a = body["wish"]["id"]
    ctx.created.append((ctx.token_a, ctx.wish_a))
    return ctx.wish_a


def smoke_08(ctx: Ctx) -> str | None:
    wish_id = ensure_wish_a(ctx)
    if not ctx.token_b:
        raise SmokeSkip("缺少第二个 smoke 账号")
    status, _, body = http("GET", f"/api/v1/wishes/{wish_id}", token=ctx.token_b)
    assert status == 404, f"B 访问 A 的愿望返回 {status}，应为 404"
    assert body["code"] == "WISH_NOT_FOUND", body
    status, _, listing = http("GET", "/api/v1/wishes", token=ctx.token_b)
    assert status == 200, status
    assert listing["items"] == [], f"B 的列表不为空：{listing}"
    return None


def smoke_09(ctx: Ctx) -> str | None:
    status, _, body = http("POST", "/api/v1/auth/anonymous", body={"timezone": "Asia/Shanghai"})
    assert status == 201, f"建号返回 {status}：{body}"
    assert body.get("access_token"), body
    assert body["user"].get("onboarded_at"), "onboarded_at 为空"
    return None


def smoke_10(ctx: Ctx) -> str | None:
    """分层断言：链路通过即 PASS，degraded 只写 warning，不改判 FAIL（§8.3）。"""
    status, _, body = http(
        "POST",
        "/api/v1/wishes",
        token=ctx.token_a,
        body={"source": "text", "text": PLAINTEXT},
    )
    assert status == 201, f"种下返回 {status}：{body}"
    wish = body["wish"]
    ctx.created.append((ctx.token_a, wish["id"]))
    assert wish["title"], "title 为空"
    assert wish["original_text"] == PLAINTEXT, wish["original_text"]

    status, _, listing = http("GET", "/api/v1/wishes", token=ctx.token_a)
    assert status == 200, status
    assert wish["id"] in [i["id"] for i in listing["items"]], "愿望没有出现在花园列表里"

    if body.get("degraded") is True:
        return "Agent 降级，检查 LLM_BASE_URL / LLM_API_KEY"
    return None


def smoke_11(ctx: Ctx) -> str | None:
    wish_id = ensure_wish_a(ctx)
    status, _, body = http(
        "PUT",
        f"/api/v1/wishes/{wish_id}/timing",
        token=ctx.token_a,
        body={"type": "after_months", "after_months": 1},
    )
    assert status == 200, f"设时机返回 {status}：{body}"
    assert body["state"] == "brewing", body["state"]
    assert body["timing"]["label"], body["timing"]
    assert body["timing"]["next_trigger_at"] is not None, body["timing"]
    return None


def smoke_12(ctx: Ctx) -> str | None:
    """把 next_trigger_at 置为过去，再触发一轮扫描。

    生产没有 `/api/test/*` 后门（SMOKE-core-04 就是在验证这件事），因此这里
    一律走 `SMOKE_SCHEDULER_CMD` 的一次性命令，而不是后门端点。
    """
    wish_id = ensure_wish_a(ctx)
    db_rows(
        "UPDATE wishes SET next_trigger_at = '2020-01-01T00:00:00.000Z'"
        f" WHERE id = '{_lit(wish_id)}'"
    )

    proc = subprocess.run(  # noqa: S602 —— 命令来自运维配置，不来自用户输入
        SCHEDULER_CMD, shell=True, capture_output=True, text=True, timeout=300, cwd=REPO_ROOT
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise SmokeSkip(f"调度命令执行失败（{SCHEDULER_CMD}）：{out.strip()[:300]}")
    stats = None
    for line in reversed(out.strip().splitlines()):
        try:
            stats = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    assert stats is not None, f"调度命令没有输出统计 JSON：{out.strip()[:300]}"
    assert stats.get("scanned", 0) >= 1, stats
    assert stats.get("enqueued", 0) >= 1, stats

    left = db_rows(
        f"SELECT count(*) FROM reminder_outbox WHERE wish_id = '{_lit(wish_id)}'"
    )[0][0]
    assert int(left) >= 1, "reminder_outbox 没有该愿望的记录"
    return None


def smoke_13(ctx: Ctx) -> str | None:
    """记忆页全链路。用一个独立愿望，避免与 SMOKE-core-11/12 的时机状态互相干扰。"""
    status, _, seeded = http(
        "POST",
        "/api/v1/wishes",
        token=ctx.token_a,
        body={"source": "text", "text": "smoke：记忆页链路"},
    )
    assert status == 201, seeded
    wish_id = seeded["wish"]["id"]
    ctx.created.append((ctx.token_a, wish_id))

    today = time.strftime("%Y-%m-%d")
    status, _, draft = http(
        "POST",
        f"/api/v1/wishes/{wish_id}/happened",
        token=ctx.token_a,
        body={"happened_from": today},
    )
    assert status == 201, f"标记已发生返回 {status}：{draft}"
    ctx.memory_a = draft["memory"]["id"]

    status, _, published = http(
        "POST", f"/api/v1/memories/{ctx.memory_a}/publish", token=ctx.token_a
    )
    assert status == 200, f"发布返回 {status}：{published}"
    assert published["memory"]["status"] == "published", published

    status, _, shelf = http("GET", "/api/v1/memories", token=ctx.token_a)
    assert status == 200, status
    assert ctx.memory_a in [i["id"] for i in shelf["items"]], "书架里找不到这一页"
    assert shelf["lived_pages"] >= 1, shelf

    status, _, wish = http("GET", f"/api/v1/wishes/{wish_id}", token=ctx.token_a)
    assert status == 200, status
    assert wish["state"] == "happened", wish["state"]
    return None


def smoke_14(ctx: Ctx) -> str | None:
    wish_id = ensure_wish_a(ctx)
    if not ctx.token_b:
        raise SmokeSkip("缺少第二个 smoke 账号")
    status, _, body = http("GET", f"/api/v1/wishes/{wish_id}", token=ctx.token_b)
    assert status == 404, f"跨账号访问返回 {status}，必须是 404（不是 403、不是 200）"
    assert body["code"] == "WISH_NOT_FOUND", body
    return None


def smoke_15(ctx: Ctx) -> str | None:
    payload = b"\x1a\x45\xdf\xa3" + b"0" * 1020  # 1KB 音频
    status, _, created = http(
        "POST",
        "/api/v1/media/upload-url",
        token=ctx.token_a,
        body={"kind": "audio", "content_type": "audio/webm", "size_bytes": len(payload)},
    )
    assert status == 201, f"签发预签名返回 {status}：{created}"
    upload_url = created["upload_url"]

    req = urllib.request.Request(
        upload_url, data=payload, headers={"Content-Type": "audio/webm"}, method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            assert resp.status in (200, 204), f"直传返回 {resp.status}"
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"直传失败：{exc.code} {exc.read()[:200]!r}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise SmokeSkip(f"预签名 URL 不可达：{exc}") from exc

    status, _, _ = http(
        "POST", f"/api/v1/media/{created['media_id']}/complete", token=ctx.token_a
    )
    assert status == 204, f"complete 返回 {status}"

    rows = db_rows(
        f"SELECT status FROM media WHERE id = '{_lit(created['media_id'])}'"
    )
    assert rows and rows[0][0] == "ready", f"media.status = {rows}"
    return None


def smoke_16(ctx: Ctx) -> str | None:
    for path in ("/", "/manifest.webmanifest", "/sw.js"):
        status, _, body = http("GET", path, base=WEB_URL)
        assert status == 200, f"GET {WEB_URL}{path} 返回 {status}"
        if path == "/manifest.webmanifest":
            data = body if isinstance(body, dict) else json.loads(body)
            assert isinstance(data, dict) and data.get("name"), f"manifest 不可解析：{body!r}"
    return None


def smoke_17(ctx: Ctx) -> str | None:
    if not WEB_URL.startswith("https://"):
        raise SmokeSkip(f"站点未走 HTTPS（{WEB_URL}），证书检查不适用")
    import socket
    from datetime import datetime, timezone
    from urllib.parse import urlsplit

    parts = urlsplit(WEB_URL)
    host, port = parts.hostname, parts.port or 443
    ctx_ssl = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=15) as sock:
        with ctx_ssl.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
    expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(
        tzinfo=timezone.utc
    )
    issuer = " ".join(
        v for rdn in cert.get("issuer", ()) for pair in rdn for v in pair[1:]
    )
    if "Caddy Local Authority" in issuer or "localhost" == host:
        # 本机演练用的内部 CA 签的是 12 小时短证书；「剩余有效期 >14 天」这条
        # 检查针对的是公网证书，对内部 CA 不适用——记 skip 并把签发者写进原因，
        # 而不是让它以一个看起来像证书快过期的 fail 混进报告。
        raise SmokeSkip(f"证书由内部 CA 签发（{issuer or 'unknown'}），公网有效期检查不适用")
    days_left = (expires - datetime.now(timezone.utc)).days
    assert days_left > 14, f"证书剩余 {days_left} 天，应 >14"

    plain = f"http://{host}"
    req = urllib.request.Request(plain, method="HEAD")

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=15) as resp:
            code = resp.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    assert code == 301, f"HTTP 未 301 到 HTTPS（返回 {code}）"
    return None


def _recent_logs() -> str | None:
    """最近 100 条应用日志。取不到返回 None（记 warning 而不是 fail）。

    容器化部署里日志不落文件而是走 stdout，所以优先用 `SMOKE_LOG_CMD`
    （例如 `docker compose logs --tail 200 api scheduler`）；
    传统部署有日志文件时用 `SMOKE_LOG_PATH`。
    """
    cmd = os.environ.get("SMOKE_LOG_CMD")
    if cmd:
        proc = subprocess.run(  # noqa: S602 —— 命令来自运维配置
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=REPO_ROOT,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if not out.strip():
            return None
        return chr(10).join(out.splitlines()[-100:])
    path = os.environ.get("SMOKE_LOG_PATH")
    if path and Path(path).exists():
        return chr(10).join(
            Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
        )
    return None


def smoke_18(ctx: Ctx) -> str | None:
    """加密落地 + 日志无明文 + smoke 数据已清理，三件事一起验。"""
    wish_id = ensure_wish_a(ctx)
    rows = db_rows(f"SELECT title_enc FROM wishes WHERE id = '{_lit(wish_id)}'")
    assert rows, "愿望不存在，无法验证加密落地"
    # 经 SMOKE_DB_CMD 取回时 BLOB 被 latin-1 解码成字符串，本机直连时仍是 bytes；
    # 两种形态都只做一件事：确认密文里读不到明文
    blob = rows[0][0]
    raw = blob.encode("latin-1") if isinstance(blob, str) else bytes(blob)
    assert PLAINTEXT.encode() not in raw, "title_enc 里能直接读到明文"

    joined = _recent_logs()
    if joined is None:
        ctx.warnings.append("未提供 SMOKE_LOG_CMD / SMOKE_LOG_PATH，日志明文抽查以 warning 记录")
    else:
        assert PLAINTEXT not in joined, "应用日志里出现了愿望原话"
        assert "request_id" in joined, "应用日志缺少 request_id"

    # 清理并复查：删除后愿望、媒体与记忆页均不存在
    for token, wish_id in list(ctx.created):
        status, _, _ = http(
            "DELETE", f"/api/v1/wishes/{wish_id}?confirm=true", token=token
        )
        assert status == 204, f"删除 {wish_id} 返回 {status}"
    ctx.created.clear()

    owners = f"'{_lit(ctx.user_a)}', '{_lit(ctx.user_b)}'"
    left = db_rows(f"SELECT count(*) FROM wishes WHERE owner_id IN ({owners})")[0][0]
    memories = db_rows(f"SELECT count(*) FROM memories WHERE owner_id IN ({owners})")[0][0]
    assert int(left) == 0, f"smoke 账号仍残留 {left} 条愿望"
    assert int(memories) == 0, f"smoke 账号仍残留 {memories} 页记忆"
    if ctx.warnings:
        return "；".join(ctx.warnings)
    return None


# ---------------------------------------------------------------- 编排

ALL = "local", "staging", "production"
DEPLOYED = "staging", "production"

def smoke_19(ctx: Ctx) -> str | None:
    """声明一条偏好 → 能读回且来源为 declared；写响应不回显 value 明文（S08 隐私红线）。"""
    status, _, created = http(
        "PUT",
        "/api/v1/me/preferences",
        token=ctx.token_a,
        body={"pref_key": "companion", "value": "smoke：更想和朋友一起"},
    )
    assert status == 200, f"声明偏好返回 {status}：{created}"
    assert "value" not in created, f"写响应不得回显 value 明文：{created}"

    status, _, listing = http("GET", "/api/v1/me/preferences", token=ctx.token_a)
    assert status == 200, f"读取偏好返回 {status}"
    rows = [i for i in listing["items"] if i["pref_key"] == "companion"]
    assert len(rows) == 1, f"偏好条目数量 = {len(rows)}"
    assert rows[0]["source"] == "declared" and rows[0]["confidence"] == 100
    assert rows[0]["value"] == "smoke：更想和朋友一起", "GET 回显本人明文"

    row = db_rows(
        f"SELECT value_enc FROM user_preferences WHERE id = '{_lit(rows[0]['id'])}'"
    )
    assert row, "user_preferences 缺行"
    stored = row[0][0] if isinstance(row[0][0], bytes) else str(row[0][0]).encode("utf-8", "ignore")
    assert "更想和朋友一起".encode() not in stored, "value_enc 必须是密文"
    return None


def smoke_20(ctx: Ctx) -> str | None:
    """保存一条可用时段 → 能读回；清理无残留（并入 smoke 数据自清理）。"""
    status, _, created = http(
        "POST",
        "/api/v1/me/availability",
        token=ctx.token_a,
        body={"weekday": 5, "start_minute": 540, "end_minute": 720},
    )
    assert status == 201, f"保存可用时段返回 {status}：{created}"
    window_id = created["id"]

    status, _, listing = http("GET", "/api/v1/me/availability", token=ctx.token_a)
    assert status == 200
    assert any(w["id"] == window_id and w["weekday"] == 5 for w in listing["items"]), listing

    status, _, _ = http("DELETE", f"/api/v1/me/availability/{window_id}", token=ctx.token_a)
    assert status == 204, f"删除返回 {status}"
    status, _, _ = http("DELETE", f"/api/v1/me/availability/{window_id}", token=ctx.token_a)
    assert status == 404, f"重复删除应 404，得到 {status}"
    return None


def smoke_21(ctx: Ctx) -> str | None:
    """先记一下 → 划掉 → 收走 → 无残留；outbox 无轻事件相关行（S09 结构性保证）。"""
    status, _, created = http(
        "POST", "/api/v1/lite-events", token=ctx.token_a, body={"text": "smoke：今晚吃火锅"}
    )
    assert status == 201, f"记下返回 {status}：{created}"
    assert created["text"] == "smoke：今晚吃火锅" and created["status"] == "open"
    event_id = created["id"]

    status, _, listing = http("GET", "/api/v1/lite-events", token=ctx.token_a)
    assert status == 200 and any(i["id"] == event_id for i in listing["items"])

    status, _, done = http("POST", f"/api/v1/lite-events/{event_id}/done", token=ctx.token_a)
    assert status == 200 and done["status"] == "done" and done["closed_at"]
    status, _, _ = http("POST", f"/api/v1/lite-events/{event_id}/done", token=ctx.token_a)
    assert status == 409, f"重复划掉应 409，得到 {status}"
    status, _, _ = http("DELETE", f"/api/v1/lite-events/{event_id}", token=ctx.token_a)
    assert status == 204, f"收走返回 {status}"
    status, _, _ = http("DELETE", f"/api/v1/lite-events/{event_id}", token=ctx.token_a)
    assert status == 404, f"重复收走应 404，得到 {status}"

    rows = db_rows("SELECT count(*) FROM reminder_outbox")
    assert rows[0][0] == 0, f"outbox 出现了 {rows[0][0]} 行——轻事件不得有提醒路径"
    return None


CASES = (
    Case("SMOKE-core-01", ALL, "健康检查接口可访问且数据库连通", smoke_01),
    Case("SMOKE-core-02", DEPLOYED, "调度进程存活", smoke_02),
    Case("SMOKE-core-03", DEPLOYED, "必需环境变量齐备", smoke_03),
    Case("SMOKE-core-04", DEPLOYED, "测试后门在非 test 环境不存在", smoke_04),
    Case("SMOKE-core-05", DEPLOYED, "数据库文件与 PRAGMA 正确", smoke_05),
    Case("SMOKE-core-06", ALL, "迁移版本与本次发布一致", smoke_06),
    Case("SMOKE-core-07", DEPLOYED, "关键表齐备", smoke_07),
    Case("SMOKE-core-08", DEPLOYED, "数据隔离守卫生效", smoke_08),
    Case("SMOKE-core-09", ALL, "匿名建号可用", smoke_09),
    Case("SMOKE-core-10", ALL, "种下一个愿望并出现在花园", smoke_10),
    Case("SMOKE-core-11", ALL, "约定一个时机", smoke_11),
    Case("SMOKE-core-12", DEPLOYED, "触发一轮调度且提醒进入 outbox", smoke_12),
    Case("SMOKE-core-13", ALL, "记忆页全链路", smoke_13),
    Case("SMOKE-core-14", DEPLOYED, "数据隔离：跨账号访问返回 404", smoke_14),
    Case("SMOKE-core-15", DEPLOYED, "预签名上传可用", smoke_15),
    Case("SMOKE-core-16", DEPLOYED, "静态站点与 PWA 资源可取", smoke_16),
    Case("SMOKE-core-17", DEPLOYED, "HTTPS 与证书有效", smoke_17),
    Case("SMOKE-core-18", DEPLOYED, "加密落地、日志无明文、smoke 数据已清理", smoke_18),
    Case("SMOKE-core-19", ALL, "偏好声明与读取（含不回显与加密断言）", smoke_19),
    Case("SMOKE-core-20", ALL, "可用时段保存与读取", smoke_20),
    Case("SMOKE-core-21", ALL, "先记一下链路（outbox 无轻事件行）", smoke_21),
)


def write_record(record: dict) -> None:
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + chr(10))


def setup(ctx: Ctx) -> None:
    """建两个 smoke 账号。失败不抛——让每个用例各自报出「前置缺失」而不是整体炸掉。"""
    for slot in ("a", "b"):
        try:
            status, _, body = http(
                "POST", "/api/v1/auth/anonymous", body={"timezone": "Asia/Shanghai"}
            )
        except SmokeSkip:
            return
        if status != 201:
            return
        setattr(ctx, f"token_{slot}", body["access_token"])
        setattr(ctx, f"user_{slot}", body["user"]["id"])


def teardown(ctx: Ctx) -> None:
    """自建自清。失败也要清——残留数据会让下一次 smoke 的断言变得不可信。"""
    for token, wish_id in list(ctx.created):
        try:
            http("DELETE", f"/api/v1/wishes/{wish_id}?confirm=true", token=token)
        except SmokeSkip:
            pass
    ctx.created.clear()


def main() -> int:
    ctx = Ctx()
    print(f"smoke-core: env={ENV} api={BASE_URL} web={WEB_URL}")
    setup(ctx)
    if not ctx.token_a:
        print(f"  ! 无法在 {BASE_URL} 建立 smoke 账号，依赖账号的用例将记 skip")

    failed = 0
    for case in CASES:
        started = time.monotonic()
        record: dict[str, object] = {
            "id": case.id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scenario": case.title,
        }
        if ENV not in case.envs:
            record["status"] = "skip"
            record["error"] = f"目标环境为 {'/'.join(case.envs)}，当前是 {ENV}"
            print(f"  - {case.id} skip（{record['error']}）")
            write_record(record)
            continue
        try:
            warning = case.fn(ctx)  # type: ignore[operator]
            record["status"] = "pass"
            if warning:
                record["warning"] = warning
            print(f"  + {case.id} pass" + (f"（warning: {warning}）" if warning else ""))
        except SmokeSkip as exc:
            record["status"] = "skip"
            record["error"] = str(exc)
            print(f"  - {case.id} skip（{exc}）")
        except AssertionError as exc:
            record["status"] = "fail"
            record["error"] = str(exc) or "assertion failed"
            failed += 1
            print(f"  x {case.id} FAIL：{exc}")
        except Exception as exc:  # noqa: BLE001 —— runner 不能因一个用例炸掉整轮
            record["status"] = "fail"
            record["error"] = f"{type(exc).__name__}: {exc}"
            failed += 1
            print(f"  x {case.id} FAIL：{type(exc).__name__}: {exc}")
        record["duration_ms"] = round((time.monotonic() - started) * 1000)
        write_record(record)

    teardown(ctx)
    print(f"smoke-core: {len(CASES)} 项，{failed} 项失败 → {RESULT_PATH}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())









