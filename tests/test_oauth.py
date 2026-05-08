"""Google OAuth sign-in tests with a stubbed provider client."""
from __future__ import annotations

from typing import Any

import pytest
from flask import Flask

from stride.extensions import oauth
from stride.models import OAuthIdentity, User


class _StubClient:
    """Duck-typed substitute for an Authlib OAuth client."""

    def __init__(self, token: dict[str, Any]):
        self._token = token

    def authorize_redirect(self, redirect_uri: str):
        from flask import redirect
        return redirect(f"https://provider.example/authorize?redirect_uri={redirect_uri}")

    def authorize_access_token(self) -> dict[str, Any]:
        return self._token


@pytest.fixture
def stub_provider(monkeypatch):
    def _make(provider: str, *, sub: str, email: str | None, name: str | None):
        userinfo = {"sub": sub}
        if email is not None:
            userinfo["email"] = email
        if name is not None:
            userinfo["name"] = name
        client = _StubClient(token={"userinfo": userinfo})

        monkeypatch.setattr(
            oauth, "create_client",
            lambda name, _client=client: _client if name == provider else None,
        )
        return client

    return _make


@pytest.fixture(autouse=True)
def _expose_provider(app: Flask):
    """Render the Google button regardless of credentials in tests."""
    original = app.template_context_processors[None].copy()

    def _ctx() -> dict:
        return {"oauth_providers": ("google",)}

    app.template_context_processors[None].append(_ctx)
    yield
    app.template_context_processors[None] = original


class TestOAuthLoginRedirect:
    def test_redirects_to_provider(self, client, stub_provider):
        stub_provider("google", sub="g-1", email="alice@gmail.com", name="Alice")
        response = client.get("/auth/oauth/google/login", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["Location"].startswith("https://provider.example/")

    def test_unknown_provider_404(self, client):
        response = client.get("/auth/oauth/dropbox/login")
        assert response.status_code == 404

    def test_microsoft_and_facebook_404(self, client):
        # Removed providers must 404 rather than silently fall through.
        for path in ("/auth/oauth/microsoft/login",
                     "/auth/oauth/facebook/login"):
            assert client.get(path).status_code == 404

    def test_unconfigured_provider_flashes_user_friendly_message(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(oauth, "create_client", lambda name: None)
        response = client.get("/auth/oauth/google/login", follow_redirects=True)
        assert response.status_code == 200
        assert b"isn&#39;t available" in response.data or b"isn't available" in response.data
        assert b"Google" in response.data
        # No developer-facing leakage in the user-visible message.
        assert b"GOOGLE_CLIENT_ID" not in response.data
        assert b".env" not in response.data

    def test_already_logged_in_redirected_to_index(
        self, client, make_user, login, stub_provider
    ):
        make_user("alice")
        login("alice")
        stub_provider("google", sub="g-1", email="alice@gmail.com", name="Alice")
        response = client.get("/auth/oauth/google/login", follow_redirects=False)
        assert response.status_code == 302
        assert "provider.example" not in response.headers["Location"]


class TestGoogleCallback:
    def test_creates_new_user(self, client, stub_provider):
        stub_provider(
            "google", sub="g-42",
            email="newperson@gmail.com", name="New Person",
        )
        response = client.get("/auth/oauth/google/callback", follow_redirects=True)
        assert response.status_code == 200
        assert User.query.count() == 1
        assert OAuthIdentity.query.count() == 1
        identity = OAuthIdentity.query.one()
        assert identity.provider == "google"
        assert identity.provider_user_id == "g-42"
        assert identity.user.email == "newperson@gmail.com"

    def test_oauth_user_has_no_password(self, client, stub_provider):
        stub_provider("google", sub="g-1", email="alice@gmail.com", name="Alice")
        client.get("/auth/oauth/google/callback")
        user = User.query.one()
        assert user.password_hash is None
        assert not user.check_password("")
        assert not user.check_password("anything")

    def test_existing_identity_logs_in(self, client, stub_provider, db):
        u = User(username="alice", email="alice@gmail.com", password_hash=None)
        db.session.add(u)
        db.session.flush()
        db.session.add(OAuthIdentity(
            user_id=u.id, provider="google",
            provider_user_id="g-1", email="alice@gmail.com",
        ))
        db.session.commit()

        stub_provider("google", sub="g-1", email="alice@gmail.com", name="Alice")
        response = client.get("/auth/oauth/google/callback", follow_redirects=True)
        assert response.status_code == 200
        assert User.query.count() == 1
        assert OAuthIdentity.query.count() == 1
        assert client.get("/dashboard/").status_code == 200

    def test_links_to_existing_email_account(self, client, stub_provider, make_user):
        make_user("alice", email="alice@gmail.com")

        stub_provider("google", sub="g-1", email="alice@gmail.com", name="Alice")
        client.get("/auth/oauth/google/callback")

        assert User.query.count() == 1
        user = User.query.one()
        assert user.password_hash is not None
        assert user.oauth_identities.count() == 1
        assert user.oauth_identities.first().provider == "google"

    def test_username_collision_disambiguated(self, client, stub_provider, make_user):
        make_user("alice", email="alice@formfilled.com")
        stub_provider("google", sub="g-9",
                      email="alice@gmail.com", name="alice")
        client.get("/auth/oauth/google/callback")

        users = User.query.order_by(User.id).all()
        assert len(users) == 2
        assert {u.username for u in users} == {"alice", "alice_2"}

    def test_username_sanitised(self, client, stub_provider):
        stub_provider("google", sub="g-7",
                      email="a@b.com", name="Alice McSpace!#")
        client.get("/auth/oauth/google/callback")
        user = User.query.one()
        assert "!" not in user.username
        assert "#" not in user.username
        assert " " not in user.username

    def test_no_email_blocks_account_creation(self, client, stub_provider):
        stub_provider("google", sub="g-noemail", email=None, name="No Email")
        response = client.get("/auth/oauth/google/callback", follow_redirects=True)
        assert User.query.count() == 0
        assert b"did not share an email" in response.data

    def test_no_subject_blocks_login(self, client, stub_provider):
        stub_provider("google", sub=None, email="x@y.com", name="X")
        response = client.get("/auth/oauth/google/callback", follow_redirects=True)
        assert User.query.count() == 0
        assert b"no account identifier" in response.data


class TestCallbackResilience:
    def test_token_exchange_failure_is_handled(self, client, monkeypatch):
        class _BadClient:
            def authorize_access_token(self):
                raise RuntimeError("bad state")

        monkeypatch.setattr(
            oauth, "create_client",
            lambda name: _BadClient() if name == "google" else None,
        )
        response = client.get("/auth/oauth/google/callback", follow_redirects=True)
        assert User.query.count() == 0
        assert b"failed" in response.data.lower()


class TestTemplateButtons:
    def test_login_page_renders_google_button(self, client):
        response = client.get("/auth/login")
        assert b"Sign in with Google" in response.data
        # Removed providers must not appear.
        assert b"Microsoft" not in response.data
        assert b"Facebook" not in response.data

    def test_signup_page_renders_google_button(self, client):
        response = client.get("/auth/signup")
        assert b"Sign up with Google" in response.data
        assert b"Microsoft" not in response.data
        assert b"Facebook" not in response.data
