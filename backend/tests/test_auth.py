"""认证相关的单元测试：邮箱/密码策略、注册登录、限流、会话、改密。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import auth  # noqa: E402


class TempStoreMixin:
    """每个用例一个临时库，互不污染；轮数调低让测试跑得快。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="chili-auth-test-")
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "auth.db"
        self.store = auth.AuthStore(self.db)
        self.service = auth.AuthService(self.store, rounds=1200)

    def register(self, email="User@Example.com", password="RitA2024x", ip="127.0.0.1"):
        return self.service.register(email, password, ip=ip, user_agent="unittest")


class EmailTests(unittest.TestCase):
    def test_trims_and_lowercases(self):
        self.assertEqual(auth.normalise_email("  MiXeD@Example.COM "), "mixed@example.com")

    def test_rejects_missing_at(self):
        for value in ("", "plain", "a@", "@b.com", "a@@b.com"):
            with self.assertRaises(auth.AuthError):
                auth.normalise_email(value)

    def test_rejects_bad_domain(self):
        for value in ("a@b", "a@b.", "a@-b.com", "a@b..com", "a@b.c"):
            with self.assertRaises(auth.AuthError):
                auth.normalise_email(value)

    def test_rejects_dotted_edges(self):
        for value in (".a@b.com", "a.@b.com", "a..b@b.com"):
            with self.assertRaises(auth.AuthError):
                auth.normalise_email(value)

    def test_rejects_non_string(self):
        for value in (None, 123, [], {}):
            with self.assertRaises(auth.AuthError):
                auth.normalise_email(value)

    def test_rejects_too_long(self):
        with self.assertRaises(auth.AuthError):
            auth.normalise_email("a" * 250 + "@example.com")

    def test_keeps_plus_and_dots(self):
        self.assertEqual(
            auth.normalise_email("first.last+tag@example.co.uk"),
            "first.last+tag@example.co.uk",
        )


class PasswordPolicyTests(unittest.TestCase):
    def test_accepts_reasonable_password(self):
        self.assertEqual(auth.validate_password("RitA2024x"), "RitA2024x")

    def test_rejects_short(self):
        with self.assertRaises(auth.AuthError) as ctx:
            auth.validate_password("ab12")
        self.assertEqual(ctx.exception.code, "password_weak")

    def test_rejects_too_long(self):
        with self.assertRaises(auth.AuthError):
            auth.validate_password("a1" * 100)

    def test_rejects_single_class(self):
        for value in ("abcdefgh", "12345678x"[:8], "11111111"):
            with self.assertRaises(auth.AuthError):
                auth.validate_password(value)

    def test_rejects_common_password(self):
        with self.assertRaises(auth.AuthError):
            auth.validate_password("abc12345")

    def test_rejects_edge_spaces(self):
        with self.assertRaises(auth.AuthError):
            auth.validate_password(" RitA2024x ")

    def test_rejects_email_prefix(self):
        with self.assertRaises(auth.AuthError):
            auth.validate_password("user2024", "user2024@example.com")

    def test_rejects_non_string(self):
        with self.assertRaises(auth.AuthError):
            auth.validate_password(None)


class HashTests(unittest.TestCase):
    def test_roundtrip(self):
        stored = auth.make_password_hash("RitA2024x", rounds=1000)
        self.assertTrue(stored.startswith("pbkdf2_sha256$1000$"))
        self.assertTrue(auth.verify_password("RitA2024x", stored))

    def test_wrong_password(self):
        stored = auth.make_password_hash("RitA2024x", rounds=1000)
        self.assertFalse(auth.verify_password("RitA2024y", stored))

    def test_salt_makes_hashes_unique(self):
        first = auth.make_password_hash("RitA2024x", rounds=1000)
        second = auth.make_password_hash("RitA2024x", rounds=1000)
        self.assertNotEqual(first, second)

    def test_rejects_malformed_hash(self):
        for stored in ("", "nope", "pbkdf2_sha256$0$aa$bb", "md5$1$aa$bb", None):
            self.assertFalse(auth.verify_password("RitA2024x", stored))


class RegisterTests(TempStoreMixin, unittest.TestCase):
    def test_creates_user(self):
        user = self.register()
        self.assertEqual(user["email"], "user@example.com")
        self.assertIsNone(user["last_login_at"])
        self.assertEqual(self.store.count_users(), 1)

    def test_duplicate_email_is_conflict(self):
        self.register()
        with self.assertRaises(auth.AuthError) as ctx:
            self.register(email="USER@example.com")
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(ctx.exception.code, "email_taken")

    def test_password_is_not_stored_in_plain_text(self):
        self.register(password="RitA2024x")
        row = self.store.find_by_email("user@example.com")
        self.assertNotIn("RitA2024x", row["password_hash"])

    def test_register_quota(self):
        for index in range(auth.REGISTER_PER_HOUR):
            self.register(email=f"user{index}@example.com", ip="10.0.0.1")
        with self.assertRaises(auth.AuthError) as ctx:
            self.register(email="overflow@example.com", ip="10.0.0.1")
        self.assertEqual(ctx.exception.status, 429)

    def test_quota_is_per_ip(self):
        for index in range(auth.REGISTER_PER_HOUR):
            self.register(email=f"user{index}@example.com", ip="10.0.0.1")
        self.register(email="other@example.com", ip="10.0.0.2")
        self.assertEqual(self.store.count_users(), auth.REGISTER_PER_HOUR + 1)


class LoginTests(TempStoreMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.register()

    def test_success_sets_last_login(self):
        token, expires, user = self.service.login("user@example.com", "RitA2024x")
        self.assertTrue(token)
        self.assertGreater(expires, 0)
        self.assertEqual(user["email"], "user@example.com")
        self.assertIsNotNone(user["last_login_at"])

    def test_email_is_case_insensitive(self):
        token, _, user = self.service.login("USER@Example.com", "RitA2024x")
        self.assertTrue(token)
        self.assertEqual(user["email"], "user@example.com")

    def test_wrong_password_counts_down(self):
        for expected in (4, 3, 2, 1):
            with self.assertRaises(auth.AuthError) as ctx:
                self.service.login("user@example.com", "Wrong2024")
            self.assertEqual(ctx.exception.status, 401)
            self.assertIn(f"还能再试 {expected} 次", ctx.exception.message)

    def test_lockout_after_max_failures(self):
        for _ in range(auth.MAX_EMAIL_FAILS):
            with self.assertRaises(auth.AuthError):
                self.service.login("user@example.com", "Wrong2024")
        with self.assertRaises(auth.AuthError) as ctx:
            self.service.login("user@example.com", "RitA2024x")
        self.assertEqual(ctx.exception.status, 429)
        self.assertEqual(ctx.exception.code, "too_many_attempts")

    def test_lockout_is_per_email(self):
        self.register(email="other@example.com", password="Other2024x")
        for _ in range(auth.MAX_EMAIL_FAILS):
            with self.assertRaises(auth.AuthError):
                self.service.login("user@example.com", "Wrong2024")
        token, _, _ = self.service.login("other@example.com", "Other2024x")
        self.assertTrue(token)

    def test_unknown_email_uses_same_message(self):
        with self.assertRaises(auth.AuthError) as missing:
            self.service.login("nobody@example.com", "RitA2024x")
        with self.assertRaises(auth.AuthError) as wrong:
            self.service.login("user@example.com", "Wrong2024")
        self.assertEqual(missing.exception.code, wrong.exception.code)
        self.assertEqual(
            missing.exception.message.replace(" 4 ", " 4 "),
            wrong.exception.message,
        )

    def test_malformed_email_does_not_leak(self):
        with self.assertRaises(auth.AuthError) as ctx:
            self.service.login("not-an-email", "RitA2024x")
        self.assertEqual(ctx.exception.status, 401)

    def test_empty_password(self):
        with self.assertRaises(auth.AuthError):
            self.service.login("user@example.com", "")


class SessionTests(TempStoreMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.register()
        self.token, self.expires, _ = self.service.login("user@example.com", "RitA2024x")

    def test_current_user(self):
        user = self.service.current_user(self.token)
        self.assertEqual(user["email"], "user@example.com")

    def test_unknown_token(self):
        self.assertIsNone(self.service.current_user("nope"))
        self.assertIsNone(self.service.current_user(None))

    def test_logout_invalidates(self):
        self.service.logout(self.token)
        self.assertIsNone(self.service.current_user(self.token))

    def test_database_stores_hash_only(self):
        with self.store._conn() as conn:
            rows = conn.execute("SELECT token_hash FROM sessions").fetchall()
        for row in rows:
            self.assertNotEqual(row["token_hash"], self.token)
            self.assertEqual(row["token_hash"], auth._token_hash(self.token))

    def test_expired_session_is_rejected(self):
        with self.store._conn() as conn:
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                (auth._now() - 10, auth._token_hash(self.token)),
            )
            conn.commit()
        self.assertIsNone(self.service.current_user(self.token))

    def test_expired_session_is_purged(self):
        with self.store._conn() as conn:
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                (auth._now() - 10, auth._token_hash(self.token)),
            )
            conn.commit()
        self.assertEqual(self.store.purge_expired(), 1)
        self.assertEqual(self.store.count_sessions(), 0)

    def test_old_session_is_renewed(self):
        old_expiry = auth._now() + 60
        with self.store._conn() as conn:
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                (old_expiry, auth._token_hash(self.token)),
            )
            conn.commit()
        self.assertIsNotNone(self.service.current_user(self.token))
        row = self.store.find_session(auth._token_hash(self.token))
        self.assertGreater(row["expires_at"], old_expiry)

    def test_fresh_session_is_not_extended(self):
        before = self.store.find_session(auth._token_hash(self.token))["expires_at"]
        self.service.current_user(self.token)
        after = self.store.find_session(auth._token_hash(self.token))["expires_at"]
        self.assertEqual(before, after)


class ResetPasswordTests(TempStoreMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.register()

    def test_reset_changes_password_and_drops_sessions(self):
        token, _, _ = self.service.login("user@example.com", "RitA2024x")
        self.service.reset_password("user@example.com", "NewPass2025")
        self.assertIsNone(self.service.current_user(token))
        with self.assertRaises(auth.AuthError):
            self.service.login("user@example.com", "RitA2024x")
        new_token, _, _ = self.service.login("user@example.com", "NewPass2025")
        self.assertTrue(new_token)

    def test_reset_unknown_user(self):
        with self.assertRaises(auth.AuthError) as ctx:
            self.service.reset_password("nobody@example.com", "NewPass2025")
        self.assertEqual(ctx.exception.status, 404)

    def test_reset_enforces_policy(self):
        with self.assertRaises(auth.AuthError):
            self.service.reset_password("user@example.com", "12345678")


class CookieTests(unittest.TestCase):
    def test_parse_cookie(self):
        header = "a=1; chili_session=abc123; b=2"
        self.assertEqual(auth.parse_cookie(header), "abc123")

    def test_parse_missing(self):
        self.assertIsNone(auth.parse_cookie(""))
        self.assertIsNone(auth.parse_cookie(None))
        self.assertIsNone(auth.parse_cookie("other=1"))

    def test_cookie_flags(self):
        value = auth.build_cookie("tok", auth._now() + 60)
        self.assertIn("HttpOnly", value)
        self.assertIn("SameSite=Lax", value)
        self.assertIn("Path=/", value)
        self.assertNotIn("Secure", value)
        self.assertIn("Secure", auth.build_cookie("tok", auth._now() + 60, secure=True))

    def test_logout_cookie_expires(self):
        value = auth.build_logout_cookie()
        self.assertIn("Max-Age=0", value)


class SQLInjectionTests(TempStoreMixin, unittest.TestCase):
    def test_email_with_quotes_is_rejected_not_executed(self):
        payloads = [
            "a' OR '1'='1@example.com",
            "x'; DROP TABLE users; --@example.com",
            '" OR 1=1 --@example.com',
        ]
        for payload in payloads:
            with self.assertRaises(auth.AuthError):
                self.service.register(payload, "RitA2024x")
        self.assertEqual(self.store.count_users(), 0)

    def test_login_payload_still_errors(self):
        with self.assertRaises(auth.AuthError):
            self.service.login("' OR 1=1 --", "RitA2024x")
        self.assertEqual(self.store.count_users(), 0)


class DemoAccountTests(TempStoreMixin, unittest.TestCase):
    def test_首次调用创建演示账号(self):
        result = self.service.ensure_demo()
        self.assertEqual(result, {"created": True, "reset": False})
        token, _expires, user = self.service.login(auth.DEMO_EMAIL, auth.DEMO_PASSWORD)
        self.assertTrue(token)
        self.assertEqual(user["email"], auth.DEMO_EMAIL)

    def test_重复调用不重建也不重置(self):
        self.service.ensure_demo()
        result = self.service.ensure_demo()
        self.assertEqual(result, {"created": False, "reset": False})
        self.assertEqual(self.store.count_users(), 1)

    def test_旧账号密码对不上时拉回演示密码(self):
        self.service.register(auth.DEMO_EMAIL, "Other2024x")
        result = self.service.ensure_demo()
        self.assertEqual(result, {"created": False, "reset": True})
        token, _expires, _user = self.service.login(auth.DEMO_EMAIL, auth.DEMO_PASSWORD)
        self.assertTrue(token)

    def test_重置密码会踢掉旧会话(self):
        user = self.service.register(auth.DEMO_EMAIL, "Other2024x")
        self.service.ensure_demo()
        self.assertEqual(self.store.count_sessions(), 0)
        self.assertTrue(user["id"])


if __name__ == "__main__":
    unittest.main()
