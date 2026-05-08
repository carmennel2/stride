"""Tests for the custom error pages."""
from __future__ import annotations


class TestErrorPages:
    def test_unknown_url_returns_custom_404(self, client):
        response = client.get("/this-page-does-not-exist")
        assert response.status_code == 404
        assert b"Page not found" in response.data
        assert b"404" in response.data

    def test_missing_subject_returns_custom_404(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/subjects/9999/edit")
        assert response.status_code == 404
        assert b"Page not found" in response.data

    def test_missing_task_returns_custom_404(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/tasks/9999")
        assert response.status_code == 404
        assert b"Page not found" in response.data

    def test_get_logout_returns_custom_405(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/auth/logout")
        assert response.status_code == 405
        assert b"isn&#39;t allowed" in response.data or b"isn't allowed" in response.data
        assert b"405" in response.data
