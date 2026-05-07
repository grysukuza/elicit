"""
Smoke tests for the Flask website using mock pipeline data.

These tests exercise the main browser and API flows without requiring external
Anthropic, Elicit, SMTP, or IMAP credentials.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest

# Configure the app before importing it so imports do not touch the developer's
# local database or start background scheduler threads.
_DB_FD, _DB_PATH = tempfile.mkstemp(prefix="elicit_app_smoke_", suffix=".db")
os.close(_DB_FD)
os.environ["AUTH_DB_PATH"] = _DB_PATH
os.environ["DISABLE_SCHEDULER"] = "1"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

import app as webapp  # noqa: E402
from meta_analysis import ProbabilityEstimates  # noqa: E402


def _mock_pipeline_output() -> dict:
    est = ProbabilityEstimates(control_event_rate=0.10, treatment_event_rate=0.07)
    est.compute_derived()
    return {
        "clinical_question": {
            "population": "adults with hypertension",
            "intervention": "home blood pressure monitoring",
            "comparison": "usual care",
            "outcome": "blood pressure control",
            "question_type": "therapeutic",
        },
        "result": {
            "pico_statement": (
                "In adults with hypertension, does home blood pressure "
                "monitoring improve control versus usual care?"
            ),
            "summary": "Mock summary paragraph.",
            "clinical_bottom_line": "Home monitoring can improve blood pressure control.",
            "evidence_quality": "Moderate",
            "probability_estimates": est.to_dict(),
            "papers_used": [
                {
                    "title": "Mock hypertension monitoring trial",
                    "authors": ["Doe J"],
                    "year": 2024,
                    "venue": "Mock Journal",
                    "abstract": "A mock abstract.",
                    "urls": ["https://example.org/mock"],
                    "doi": "10.0000/mock",
                }
            ],
        },
    }


def _csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not match:
        match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if not match:
        raise AssertionError("Could not find CSRF token in rendered HTML")
    return match.group(1)


class WebsiteSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        if os.path.exists(_DB_PATH):
            os.remove(_DB_PATH)
        webapp.auth.init_db()
        webapp._result_store.clear()
        webapp.run_pipeline = lambda question, max_papers=20: _mock_pipeline_output()
        webapp.app.config.update(TESTING=True)
        self.client = webapp.app.test_client()

    def register(self, username: str = "smokeuser", email: str = "smoke@example.test"):
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)
        token = _csrf_token(response.get_data(as_text=True))
        return self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "username": username,
                "email": email,
                "password": "password123",
                "password2": "password123",
            },
            follow_redirects=False,
        )

    def test_browser_flow_register_analyze_and_export(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/"))

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Clinical Decision Support", html)
        token = _csrf_token(html)

        response = self.client.post(
            "/analyze",
            json={"text": "Does home blood pressure monitoring help hypertension?"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Invalid or missing CSRF token.")

        response = self.client.post(
            "/analyze",
            json={"text": "Does home blood pressure monitoring help hypertension?"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(
            payload["result"]["clinical_bottom_line"],
            "Home monitoring can improve blood pressure control.",
        )
        result_id = payload["result_id"]

        response = self.client.get(f"/download?result_id={result_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/pdf")
        self.assertGreater(len(response.data), 1000)

        response = self.client.get(f"/download-references?result_id={result_id}&format=bibtex")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Mock hypertension monitoring trial", response.data)

        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertIn("API access", response.get_data(as_text=True))

    def test_api_key_flow_uses_bearer_auth_without_csrf(self) -> None:
        self.assertEqual(self.register().status_code, 302)
        user = webapp.auth.get_user_by_username("smokeuser")
        api_key = webapp.auth.regenerate_api_key(user["id"])

        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 401)

        response = self.client.get("/api/v1/me", headers={"Authorization": f"Bearer {api_key}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["username"], "smokeuser")

        response = self.client.post(
            "/api/v1/analyze",
            json={"question": "Does home BP monitoring help?"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["result"]["clinical_bottom_line"],
            "Home monitoring can improve blood pressure control.",
        )

    def test_result_downloads_are_user_scoped(self) -> None:
        self.assertEqual(self.register("first", "first@example.test").status_code, 302)
        token = _csrf_token(self.client.get("/").get_data(as_text=True))
        response = self.client.post(
            "/analyze",
            json={"text": "Does home blood pressure monitoring help hypertension?"},
            headers={"X-CSRF-Token": token},
        )
        result_id = response.get_json()["result_id"]
        self.client.get("/logout")

        self.assertEqual(self.register("second", "second@example.test").status_code, 302)
        response = self.client.get(f"/download?result_id={result_id}")
        self.assertEqual(response.status_code, 404)
        response = self.client.get(f"/download-references?result_id={result_id}&format=ris")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
