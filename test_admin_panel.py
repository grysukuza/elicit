"""Regression tests for the Flask admin panel."""

import os
import tempfile
import unittest


_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TEST_DB.close()
os.environ["AUTH_DB_PATH"] = _TEST_DB.name
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
os.environ["SCHEDULER_ENABLED"] = "0"

import auth  # noqa: E402
from app import app  # noqa: E402


class AdminPanelTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        auth.init_db()
        with auth._connect() as conn:
            conn.execute("DELETE FROM password_resets")
            conn.execute("DELETE FROM query_history")
            conn.execute("DELETE FROM users")
        self.client = app.test_client()

    def tearDown(self):
        with self.client.session_transaction() as sess:
            sess.clear()

    def _login_as(self, user_id: int) -> None:
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id

    def _csrf_token(self) -> str:
        with app.test_request_context():
            return auth.get_csrf_token()

    def test_admin_panel_requires_login(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=/admin", response.headers["Location"])

    def test_standard_user_cannot_open_admin_panel(self):
        user_id = auth.create_user("clinician", "password123", is_admin=False)
        self._login_as(user_id)

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_admin_can_view_panel_with_overview(self):
        admin_id = auth.create_user("admin", "password123", is_admin=True)
        user_id = auth.create_user("clinician", "password123", email="doc@example.org")
        auth.create_reset_token(user_id)
        self._login_as(admin_id)

        response = self.client.get("/admin")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Admin panel", html)
        self.assertIn("Total users", html)
        self.assertIn("Admins", html)
        self.assertIn("Pending resets", html)
        self.assertIn("doc@example.org", html)
        self.assertIn("/reset/", html)

    def test_admin_can_promote_demote_and_delete_users(self):
        admin_id = auth.create_user("admin", "password123", is_admin=True)
        user_id = auth.create_user("clinician", "password123", is_admin=False)
        self._login_as(admin_id)

        promote = self.client.post(
            f"/admin/users/{user_id}/admin",
            data={"csrf_token": self._csrf_token()},
        )
        self.assertEqual(promote.status_code, 302)
        self.assertEqual(auth.get_user_by_id(user_id)["is_admin"], 1)

        demote = self.client.post(
            f"/admin/users/{user_id}/admin",
            data={"csrf_token": self._csrf_token()},
        )
        self.assertEqual(demote.status_code, 302)
        self.assertEqual(auth.get_user_by_id(user_id)["is_admin"], 0)

        delete = self.client.post(
            f"/admin/users/{user_id}/delete",
            data={"csrf_token": self._csrf_token()},
        )
        self.assertEqual(delete.status_code, 302)
        self.assertIsNone(auth.get_user_by_id(user_id))


def tearDownModule():
    try:
        os.unlink(_TEST_DB.name)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    unittest.main()
