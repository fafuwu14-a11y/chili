"""邮箱 + 密码登录：SQLite 存储，SQL 只用 SQLite / MySQL 都认的写法。

上线要换 MySQL 时，只需要照着 ``AuthStore`` 再写一个类（同样那几个方法），
把 ``serve()`` 里传进去的 ``AuthService`` 换掉即可，业务代码不用动。

密码用 PBKDF2-HMAC-SHA256 加盐哈希，会话 token 只在库里存 sha256 摘要，
所以就算 ``app.db`` 被人拷走，也拿不到能直接登录的凭据。
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

# ---------------------------------------------------------------- 常量

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ROUNDS = 600_000
SALT_BYTES = 16
TOKEN_BYTES = 32

SESSION_SECONDS = 7 * 24 * 3600
SESSION_RENEW_WINDOW = SESSION_SECONDS // 2

COOKIE_NAME = "chili_session"

PASSWORD_MIN = 8
PASSWORD_MAX = 128

MAX_EMAIL_FAILS = 5
EMAIL_LOCK_SECONDS = 10 * 60
MAX_IP_FAILS = 20
IP_WINDOW_SECONDS = 10 * 60
REGISTER_PER_HOUR = 5

EMAIL_MAX = 254

_LOCAL_PART_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.\-]+$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)

# 只拦最常见的那几个；真正的强度靠长度 + 字母数字混合
_COMMON_PASSWORDS = {
    "12345678", "123456789", "1234567890", "87654321", "11111111", "00000000",
    "password", "password1", "passw0rd", "qwerty123", "qwertyuiop", "1qaz2wsx",
    "abc12345", "abcd1234", "a1234567", "aa123456", "iloveyou", "woaini1314",
    "admin123", "administrator", "letmein123", "welcome123", "wang123456",
    "zhang123456", "li12345678", "woaini520", "5201314520",
}


class AuthError(Exception):
    """任何应当变成 JSON 错误的认证问题。"""

    def __init__(self, message: str, status: int = 400, code: str = "auth_error"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


# ---------------------------------------------------------------- 校验

def normalise_email(raw) -> str:
    """去掉空白、统一小写、做 NFKC 归一化，然后校验格式。"""
    if not isinstance(raw, str):
        raise AuthError("邮箱不能为空", 400, "email_invalid")
    value = unicodedata.normalize("NFKC", raw).strip().lower()
    if not value:
        raise AuthError("邮箱不能为空", 400, "email_invalid")
    if len(value) > EMAIL_MAX:
        raise AuthError("邮箱太长了，检查一下有没有多打", 400, "email_invalid")
    if value.count("@") != 1:
        raise AuthError("邮箱格式不正确，例如 name@example.com", 400, "email_invalid")
    local, domain = value.split("@", 1)
    if not local or not domain or len(local) > 64:
        raise AuthError("邮箱格式不正确，例如 name@example.com", 400, "email_invalid")
    if not _LOCAL_PART_RE.match(local) or not _DOMAIN_RE.match(domain):
        raise AuthError("邮箱格式不正确，例如 name@example.com", 400, "email_invalid")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise AuthError("邮箱格式不正确，例如 name@example.com", 400, "email_invalid")
    return value


def validate_password(raw, email: str = "") -> str:
    """注册 / 改密时的密码策略。"""
    if not isinstance(raw, str):
        raise AuthError("密码不能为空", 400, "password_invalid")
    value = raw
    if len(value) < PASSWORD_MIN:
        raise AuthError(f"密码至少 {PASSWORD_MIN} 位", 400, "password_weak")
    if len(value) > PASSWORD_MAX:
        raise AuthError(f"密码最多 {PASSWORD_MAX} 位", 400, "password_weak")
    if value.strip() != value:
        raise AuthError("密码开头或结尾有空格，容易输错，建议去掉", 400, "password_weak")
    has_letter = any(ch.isalpha() for ch in value)
    has_digit = any(ch.isdigit() for ch in value)
    if not (has_letter and has_digit):
        raise AuthError("密码要同时包含字母和数字", 400, "password_weak")
    if value.lower() in _COMMON_PASSWORDS:
        raise AuthError("这个密码太常见了，换一个好记一点的", 400, "password_weak")
    if email:
        local = email.split("@", 1)[0]
        if local and value.lower() == local.lower():
            raise AuthError("密码不要和邮箱前缀一样", 400, "password_weak")
    return value


# ---------------------------------------------------------------- 哈希

def _hash_password(password: str, salt: bytes, rounds: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)


def make_password_hash(password: str, rounds: int = PBKDF2_ROUNDS) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _hash_password(password, salt, rounds)
    return f"{PBKDF2_ALGORITHM}${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码；格式不对一律当失败，不抛异常。"""
    try:
        algorithm, rounds_text, salt_hex, hash_hex = stored.split("$")
        if algorithm != PBKDF2_ALGORITHM:
            return False
        rounds = int(rounds_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (AttributeError, ValueError):
        return False
    if rounds <= 0 or not salt or not expected:
        return False
    digest = _hash_password(password, salt, rounds)
    return hmac.compare_digest(digest, expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


# ---------------------------------------------------------------- 限流

class Throttle:
    """按 key 记失败次数，超限就锁一段时间。

    - 邮箱桶：5 次失败锁 10 分钟（防定向爆破）
    - IP 桶：10 分钟内 20 次失败锁剩余窗口（防批量撞库）

    数据放在内存里，重启清空。本机单用户场景够用；
    真要上线多实例，把这里换成 Redis 即可（接口不用变）。
    """

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: tuple[str, str], now: float, window: float) -> list[float]:
        events = [t for t in self._events.get(key, []) if now - t < window]
        if events:
            self._events[key] = events
        else:
            self._events.pop(key, None)
        return events

    def blocked_for(self, email: str, ip: str) -> int:
        """还有多少秒被锁；0 表示没锁。"""
        now = time.time()
        with self._lock:
            email_events = self._prune(("email", email), now, EMAIL_LOCK_SECONDS)
            if len(email_events) >= MAX_EMAIL_FAILS:
                return max(1, int(EMAIL_LOCK_SECONDS - (now - email_events[0])))
            ip_events = self._prune(("ip", ip), now, IP_WINDOW_SECONDS)
            if len(ip_events) >= MAX_IP_FAILS:
                return max(1, int(IP_WINDOW_SECONDS - (now - ip_events[0])))
        return 0

    def register_failure(self, email: str, ip: str) -> None:
        now = time.time()
        with self._lock:
            self._events.setdefault(("email", email), []).append(now)
            self._events.setdefault(("ip", ip), []).append(now)

    def clear(self, email: str, ip: str) -> None:
        with self._lock:
            self._events.pop(("email", email), None)
            self._events.pop(("ip", ip), None)

    def failures(self, email: str) -> int:
        now = time.time()
        with self._lock:
            return len(self._prune(("email", email), now, EMAIL_LOCK_SECONDS))


class RegisterQuota:
    """每个 IP 每小时最多注册几个账号。"""

    def __init__(self, limit: int = REGISTER_PER_HOUR, window: float = 3600) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, ip: str) -> None:
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(ip, []) if now - t < self.window]
            self._hits[ip] = hits
        if len(hits) >= self.limit:
            raise AuthError("注册太频繁了，过一会儿再试", 429, "rate_limited")

    def hit(self, ip: str) -> None:
        with self._lock:
            self._hits.setdefault(ip, []).append(time.time())


# ---------------------------------------------------------------- 存储

SCHEMA = (
    # MySQL 迁移时：AUTOINCREMENT -> AUTO_INCREMENT，TEXT -> VARCHAR
    """
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        email         VARCHAR(254) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        created_at    INTEGER      NOT NULL,
        updated_at    INTEGER      NOT NULL,
        last_login_at INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash   CHAR(64)     PRIMARY KEY,
        user_id      INTEGER      NOT NULL,
        created_at   INTEGER      NOT NULL,
        expires_at   INTEGER      NOT NULL,
        last_seen_at INTEGER      NOT NULL,
        ip           VARCHAR(64),
        user_agent   VARCHAR(255),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions (expires_at)",
)


def _now() -> int:
    return int(time.time())


class AuthStore:
    """所有 SQL 都在这里，方便整体换库。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_schema()

    # -- 连接 ---------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _conn(self):
        """用完就关；sqlite3 的 with 只提交事务、不关连接，Windows 下会锁住文件。"""
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._write_lock, self._conn() as conn:
            for statement in SCHEMA:
                conn.execute(statement)
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """老库升级：早期版本把 salt 单独存一列，且不是这张表结构时重建。

        CREATE TABLE IF NOT EXISTS 不会修改已存在的表，所以结构变化只能自己补。
        """
        conn.commit()
        if "salt" in self._table_columns(conn, "users"):
            self._rebuild_users(conn)

        additions = (
            ("users", "updated_at", "INTEGER NOT NULL DEFAULT 0", "created_at"),
            ("sessions", "last_seen_at", "INTEGER NOT NULL DEFAULT 0", "created_at"),
        )
        for table, column, ddl, backfill in additions:
            if column in self._table_columns(conn, table):
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.execute(f"UPDATE {table} SET {column} = {backfill} WHERE {column} = 0")

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def _rebuild_users(self, conn: sqlite3.Connection) -> None:
        """旧版 users 有全 NOT NULL 的 salt 列，新代码不写它，插入必然失败。

        salt 现在编进 password_hash 字符串里，所以把表重建一次、丢掉这一列。
        旧哈希格式（salt 列 + 原始 hash）无法用新代码校验，用户需要走一次重置密码。
        """
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            CREATE TABLE users_new (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         VARCHAR(254) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                created_at    INTEGER      NOT NULL,
                updated_at    INTEGER      NOT NULL,
                last_login_at INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO users_new (id, email, password_hash, created_at, updated_at, last_login_at)
            SELECT id, email, password_hash, created_at, created_at, last_login_at FROM users
            """
        )
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_new RENAME TO users")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")

    # -- users --------------------------------------------------------
    def create_user(self, email: str, password_hash: str) -> dict:
        now = _now()
        try:
            with self._write_lock, self._conn() as conn:
                cursor = conn.execute(
                    "INSERT INTO users (email, password_hash, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?)",
                    (email, password_hash, now, now),
                )
                conn.commit()
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            if "UNIQUE" in str(exc).upper():
                raise AuthError("这个邮箱已经注册过了，直接登录就行", 409, "email_taken") from None
            raise AuthError("这个账号存不进去，稍后再试一次", 500, "store_error") from None
        return {"id": user_id, "email": email, "created_at": now}

    def find_by_email(self, email: str):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, email, password_hash, created_at, last_login_at"
                " FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        return dict(row) if row else None

    def find_by_id(self, user_id: int):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, email, created_at, last_login_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def mark_login(self, user_id: int) -> None:
        with self._write_lock, self._conn() as conn:
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), user_id))
            conn.commit()

    def set_password(self, user_id: int, password_hash: str) -> None:
        with self._write_lock, self._conn() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, _now(), user_id),
            )
            conn.commit()

    def list_users(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, email, created_at, last_login_at FROM users ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def count_users(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"]) if row else 0

    def delete_user(self, email: str) -> bool:
        with self._write_lock, self._conn() as conn:
            cursor = conn.execute("DELETE FROM users WHERE email = ?", (email,))
            conn.commit()
        return cursor.rowcount > 0

    # -- sessions -----------------------------------------------------
    def create_session(
        self,
        user_id: int,
        token_hash: str,
        expires_at: int,
        ip: str = "",
        user_agent: str = "",
    ) -> None:
        now = _now()
        with self._write_lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at,"
                " last_seen_at, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (token_hash, user_id, now, expires_at, now, ip[:64], user_agent[:255]),
            )
            conn.commit()

    def find_session(self, token_hash: str):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT s.token_hash, s.user_id, s.created_at, s.expires_at, s.last_seen_at,"
                " u.email FROM sessions s JOIN users u ON u.id = s.user_id"
                " WHERE s.token_hash = ?",
                (token_hash,),
            ).fetchone()
        return dict(row) if row else None

    def touch_session(self, token_hash: str, expires_at: int) -> None:
        with self._write_lock, self._conn() as conn:
            conn.execute(
                "UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE token_hash = ?",
                (_now(), expires_at, token_hash),
            )
            conn.commit()

    def delete_session(self, token_hash: str) -> None:
        with self._write_lock, self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            conn.commit()

    def delete_user_sessions(self, user_id: int) -> None:
        with self._write_lock, self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()

    def purge_expired(self) -> int:
        with self._write_lock, self._conn() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (_now(),))
            conn.commit()
        return cursor.rowcount

    def count_sessions(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM sessions WHERE expires_at > ?", (_now(),)).fetchone()
        return int(row["n"]) if row else 0


# ---------------------------------------------------------------- 服务

_DUMMY_HASH = make_password_hash("dummy-password-for-timing", rounds=1000)


def _public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "created_at": row["created_at"],
        "last_login_at": row.get("last_login_at"),
    }


class AuthService:
    """把存储、限流、会话拼成 server 需要的四个动作。"""

    def __init__(self, store: AuthStore, rounds: int = PBKDF2_ROUNDS) -> None:
        self.store = store
        self.rounds = rounds
        self.throttle = Throttle()
        self.register_quota = RegisterQuota()

    # -- 注册 ---------------------------------------------------------
    def register(self, email_raw, password_raw, ip: str = "", user_agent: str = "") -> dict:
        email = normalise_email(email_raw)
        password = validate_password(password_raw, email)
        self.register_quota.check(ip)
        password_hash = make_password_hash(password, rounds=self.rounds)
        user = self.store.create_user(email, password_hash)
        self.register_quota.hit(ip)
        self.throttle.clear(email, ip)
        return _public_user(user)

    # -- 登录 ---------------------------------------------------------
    def login(self, email_raw, password_raw, ip: str = "", user_agent: str = ""):
        # 邮箱格式不对也走同一个失败文案，别让攻击者用报错来探格式
        try:
            email = normalise_email(email_raw)
        except AuthError:
            email = (email_raw or "").strip().lower()[:EMAIL_MAX] if isinstance(email_raw, str) else ""

        if not isinstance(password_raw, str):
            password_raw = ""

        blocked = self.throttle.blocked_for(email, ip)
        if blocked:
            minutes = max(1, (blocked + 59) // 60)
            raise AuthError(
                f"尝试次数太多了，{minutes} 分钟后再试（也可以直接在命令行重设密码）",
                429,
                "too_many_attempts",
            )

        row = self.store.find_by_email(email) if email else None
        if row is None:
            verify_password(password_raw, _DUMMY_HASH)  # 抹平「有没有这个邮箱」的耗时差
            self._fail(email, ip)
        if row is None or not verify_password(password_raw, row["password_hash"]):
            self._fail(email, ip)

        token, expires_at = self.start_session(row["id"], ip, user_agent)
        self.throttle.clear(email, ip)
        row["last_login_at"] = _now()
        return token, expires_at, _public_user(row)

    def _fail(self, email: str, ip: str) -> None:
        self.throttle.register_failure(email, ip)
        left = MAX_EMAIL_FAILS - self.throttle.failures(email)
        if left > 0:
            message = f"邮箱或密码不对，还能再试 {left} 次"
        else:
            message = "邮箱或密码不对，试太多次了，先等 10 分钟"
        raise AuthError(message, 401, "bad_credentials")

    # -- 会话 ---------------------------------------------------------
    def start_session(self, user_id: int, ip: str = "", user_agent: str = ""):
        """建一个新会话，返回 (token, expires_at)。注册完直接登录也走这里。"""
        token = new_token()
        expires_at = _now() + SESSION_SECONDS
        self.store.create_session(user_id, _token_hash(token), expires_at, ip, user_agent)
        self.store.mark_login(user_id)
        return token, expires_at

    def current_user(self, token: str | None):
        if not token:
            return None
        row = self.store.find_session(_token_hash(token))
        if row is None:
            return None
        now = _now()
        if row["expires_at"] <= now:
            self.store.delete_session(row["token_hash"])
            return None
        # 剩余不足一半就续期，常用的用户不会突然掉线
        if row["expires_at"] - now < SESSION_RENEW_WINDOW:
            self.store.touch_session(row["token_hash"], now + SESSION_SECONDS)
        return {"id": row["user_id"], "email": row["email"], "created_at": row["created_at"]}

    def logout(self, token: str | None) -> None:
        if token:
            self.store.delete_session(_token_hash(token))

    # -- 维护 ---------------------------------------------------------
    def reset_password(self, email_raw, password_raw) -> dict:
        email = normalise_email(email_raw)
        password = validate_password(password_raw, email)
        row = self.store.find_by_email(email)
        if row is None:
            raise AuthError("没有这个邮箱的账号", 404, "user_not_found")
        self.store.set_password(row["id"], make_password_hash(password, rounds=self.rounds))
        # 改密后踢掉所有旧会话
        self.store.delete_user_sessions(row["id"])
        return {"id": row["id"], "email": row["email"]}

    def stats(self) -> dict:
        return {"users": self.store.count_users(), "sessions": self.store.count_sessions()}


# ---------------------------------------------------------------- Cookie

def parse_cookie(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value.strip() or None
    return None


def _cookie_attributes(secure: bool, max_age: int) -> str:
    bits = [f"Path=/", f"Max-Age={max_age}", "HttpOnly", "SameSite=Lax"]
    if secure:
        bits.append("Secure")
    return "; ".join(bits)


def build_cookie(token: str, expires_at: int, secure: bool = False) -> str:
    max_age = max(0, expires_at - _now())
    return f"{COOKIE_NAME}={token}; {_cookie_attributes(secure, max_age)}"


def build_logout_cookie(secure: bool = False) -> str:
    return f"{COOKIE_NAME}=; {_cookie_attributes(secure, 0)}"


# ---------------------------------------------------------------- CLI

def _main(argv: list[str]) -> int:
    import getpass
    import sys

    default_db = Path(__file__).resolve().parents[1] / "data" / "app.db"
    store = AuthStore(default_db)
    service = AuthService(store)

    command = argv[1] if len(argv) > 1 else "list"

    if command == "list":
        rows = store.list_users()
        if not rows:
            print("  还没有注册任何账号。")
            return 0
        print(f"  {len(rows)} 个账号（{default_db}）")
        for row in rows:
            last = row.get("last_login_at")
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "从未登录"
            print(f"    #{row['id']}  {row['email']}  注册于 {time.strftime('%Y-%m-%d', time.localtime(row['created_at']))}  上次登录 {stamp}")
        return 0

    if command in ("reset", "delete"):
        if len(argv) < 3:
            print(f"  用法: python -m app.auth {command} <邮箱>")
            return 2
        email = argv[2].strip().lower()
        if command == "delete":
            ok = store.delete_user(email)
            print("  已删除。" if ok else "  没有这个邮箱的账号。")
            return 0 if ok else 1
        password = getpass.getpass("  新密码（至少 8 位，含字母和数字）: ")
        again = getpass.getpass("  再输一次: ")
        if password != again:
            print("  两次输入不一致，已取消。")
            return 1
        try:
            service.reset_password(email, password)
        except AuthError as exc:
            print(f"  {exc.message}")
            return 1
        print("  密码已重设，旧的登录状态都失效了。")
        return 0

    print("  可用命令: list | reset <邮箱> | delete <邮箱>")
    return 2


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv))
