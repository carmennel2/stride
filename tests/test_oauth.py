"""OAuth sign-in tests with a stubbed provider client."""
from __future__ import annotations

from typing import Any

import pytest
from flask import Flask

from stride.extensions import oauth
from stride.models import OAuthIdentity, User


class _StubClient:
    """Duck-typed substitute for an Authlib OAuth client."""

    def __init__(self, token: dict[str, Any], graph_response: dict | None = None):
        self._token = token
        self._graph_response = graph_response

    def authorize_redirect(self, redirect_uri: str):
        from flask import redirect
        return redirect(f"https://provider.example/authorize?redirect_uri={redirect_uri}")

    def authorize_access_token(self) -> dict[str, Any]:
        return self._token

    def get(self, path: str, token: dict | None = None):
        class _Resp:
            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        return _Resp(self._graph_response or {})


@pytest.fixture
def stub_provider(monkeypatch):
    def _make(provider: str, *, sub: str, email: str | None, name: str | None):
        if provider == "facebook":
            graph = {"id": sub, "email": email, "name": name}
            client = _StubClient(token={"access_token": "stub-token"},
                                 graph_response=graph)
        else:
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
def _expose_all_providers(app: Flask):
    """Render every OAuth button regardless of credentials in tests."""
    original = app.template_context_processors[None].copy()

    def _ctx() -> dict:
        return {"oauth_providers": ("google", "microsoft", "facebook")}

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

    def test_unconfigured_provider_flashes_user_friendly_message(
        self, client, monkeypatch
    ):
        # An unconfigured provider lands on /auth/login with a flash
        # written for end users — no env-var names, no file paths.
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
        # No call to authorize — bounced straight to /
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
        # check_password should refuse anything rather than crash on None.
        assert not user.check_password("")
        assert not user.check_password("anything")

    def test_existing_identity_logs_in(self, client, stub_provider, db):
        # Pre-existing user + identity
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
        # No new user, no new identity.
        assert User.query.count() == 1
        assert OAuthIdentity.query.count() == 1
        # Session cookie now logs alice in — visit a protected page.
        assert client.get("/dashboard/").status_code == 200

    def test_links_to_existing_email_account(self, client, stub_provider, make_user):
        # Existing form-based account with a password.
        make_user("alice", email="alice@gmail.com")

        stub_provider("google", sub="g-1", email="alice@gmail.com", name="Alice")
        client.get("/auth/oauth/google/callback")

        # Same single user — but now with a Google identity attached.
        assert User.query.count() == 1
        user = User.query.one()
        assert user.password_hash is not None  # form password preserved
        assert user.oauth_identities.count() == 1
        identity = user.oauth_identities.first()
        assert identity.provider == "google"

    def test_username_collision_disambiguated(self, client, stub_provider, make_user):
        make_user("alice", email="alice@formfilled.com")
        # Same display name, different email — the OAuth flow shouldn't
        # try to overwrite or 500 on the username conflict.
        stub_provider("google", sub="g-9",
                      email="alice@gmail.com", name="alice")
        client.get("/auth/oauth/google/callback")

        users = User.query.order_by(User.id).all()
        assert len(users) == 2
        assert {u.username for u in users} == {"alice", "alice_2"}

    def test_username_sanitised(self, client, stub_provider):
        # Display name with spaces and characters that aren't URL-safe.
        stub_provider("google", sub="g-7",
                      email="a@b.com", name="Alice McSpace!#")
        client.get("/auth/oauth/google/callback")
        user = User.query.one()
        # Spaces stripped; punctuation other than dash/dot/underscore stripped.
        assert "!" not in user.username
        assert "#" not in user.username
        assert " " not in user.username

    def test_no_email_blocks_account_creation(self, client, stub_provider):
        # Some providers may withhold email. We don't create blank-email users.
        stub_provider("google", sub="g-noemail", email=None, name="No Email")
        response = client.get("/auth/oauth/google/callback", follow_redirects=True)
        assert User.query.count() == 0
        assert b"did not share an email" in response.data

    def test_no_subject_blocks_login(self, client, stub_provider):
        stub_provider("google", sub=None, email="x@y.com", name="X")
        response = client.get("/auth/oauth/google/callback", follow_redirects=True)
        assert User.query.count() == 0
        assert b"no account identifier" in response.data


class TestMicrosoftCallback:
    def test_creates_user_from_microsoft(self, client, stub_provider):
        stub_provider(
            "microsoft", sub="ms-1",
            email="bob@outlook.com", name="Bob",
        )
        client.get("/auth/oauth/microsoft/callback")
        identity = OAuthIdentity.query.one()
        assert identity.provider == "microsoft"
        assert identity.user.email == "bob@outlook.com"

    def test_falls_back_to_preferred_username(self, client, monkeypatch):
        # Microsoft sometimes omits `email` and uses preferred_username.
        token = {"userinfo": {"sub": "ms-2",
                              "preferred_username": "person@school.edu",
                              "name": "Person"}}
        monkeypatch.setattr(
            oauth, "create_client",
            lambda name: _StubClient(token) if name == "microsoft" else None,
        )
        client.get("/auth/oauth/microsoft/callback")
        assert User.query.one().email == "person@school.edu"


class TestFacebookCallback:
    def test_uses_graph_api_for_userinfo(self, client, stub_provider):
        stub_provider(
            "facebook", sub="fb-99",
            email="ana@example.com", name="Ana",
        )
        client.get("/auth/oauth/facebook/callback")
        identity = OAuthIdentity.query.one()
        assert identity.provider == "facebook"
        assert identity.provider_user_id == "fb-99"
        assert identity.user.email == "ana@example.com"


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
        # User is bounced back to login with a flash; no user created.
        assert User.query.count() == 0
        assert b"failed" in response.data.lower()


class TestTemplateButtons:
    def test_login_page_renders_provider_buttons(self, client):
        response = client.get("/auth/login")
        # All three buttons should render via the autouse fixture.
        for label in (b"Sign in with Google",
                      b"Sign in with Microsoft",
                      b"Sign in with Facebook"):
            assert label in response.data

    def test_signup_page_renders_provider_buttons(self, client):
        response = client.get("/auth/signup")
        for label in (b"Sign up with Google",
                      b"Sign up with Microsoft",
                      b"Sign up with Facebook"):
            assert label in response.data
