"""Tests for the auth blueprint: signup, login, logout, hashing."""
from __future__ import annotations

from stride.models import User

# A password that satisfies the policy (length > 8, upper, lower, special).
GOOD_PW = "Sup3rSecret!"


class TestSignup:
    def test_signup_creates_user_with_hashed_password(self, client, db):
        response = client.post(
            "/auth/signup",
            data={
                "username": "alice",
                "email": "alice@example.com",
                "password": GOOD_PW,
                "confirm_password": GOOD_PW,
                "submit": "x",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        user = User.query.filter_by(username="alice").one()
        assert user.password_hash != GOOD_PW, \
            "password must not be stored in plain text"
        assert user.password_hash.startswith(("scrypt:", "pbkdf2:")), \
            "expected werkzeug-format hash prefix"
        assert user.email == "alice@example.com"

    def test_signup_lowercases_email(self, client, db):
        client.post("/auth/signup", data={
            "username": "bob", "email": "Bob@Example.COM",
            "password": GOOD_PW, "confirm_password": GOOD_PW,
            "submit": "x",
        })
        assert User.query.filter_by(username="bob").one().email == "bob@example.com"

    def test_signup_rejects_duplicate_username(self, client, make_user):
        make_user("alice")
        response = client.post("/auth/signup", data={
            "username": "alice", "email": "different@example.com",
            "password": GOOD_PW, "confirm_password": GOOD_PW,
            "submit": "x",
        })
        assert b"already taken" in response.data

    def test_signup_rejects_duplicate_email(self, client, make_user):
        make_user("alice", email="alice@example.com")
        response = client.post("/auth/signup", data={
            "username": "newuser", "email": "alice@example.com",
            "password": GOOD_PW, "confirm_password": GOOD_PW,
            "submit": "x",
        })
        assert b"already exists" in response.data

    def test_signup_rejects_password_mismatch(self, client):
        response = client.post("/auth/signup", data={
            "username": "alice", "email": "alice@example.com",
            "password": GOOD_PW, "confirm_password": GOOD_PW + "X",
            "submit": "x",
        })
        assert b"Passwords must match" in response.data


class TestPasswordPolicy:
    """Password composition rules enforced by `strong_password`."""

    def _post_signup(self, client, password: str):
        return client.post("/auth/signup", data={
            "username": "alice", "email": "alice@example.com",
            "password": password, "confirm_password": password,
            "submit": "x",
        })

    def test_too_short_rejected(self, client):
        # Exactly 8 fails because the rule is "more than 8".
        response = self._post_signup(client, "Aa!12345")
        assert b"Password needs" in response.data
        assert b"more than 8" in response.data
        assert User.query.count() == 0

    def test_nine_chars_accepted_with_full_composition(self, client):
        # Successful signup logs the user in and 302s them to the index;
        # we don't follow_redirects so we observe the redirect directly.
        response = self._post_signup(client, "Aa!12345A")
        assert response.status_code == 302
        assert User.query.count() == 1

    def test_missing_uppercase_rejected(self, client):
        response = self._post_signup(client, "lowercase!1234")
        assert b"uppercase letter" in response.data
        assert User.query.count() == 0

    def test_missing_lowercase_rejected(self, client):
        response = self._post_signup(client, "UPPERCASE!1234")
        assert b"lowercase letter" in response.data
        assert User.query.count() == 0

    def test_missing_special_char_rejected(self, client):
        response = self._post_signup(client, "Alphanumeric99")
        assert b"special character" in response.data
        assert User.query.count() == 0

    def test_combined_failures_in_one_message(self, client):
        # Length, upper, special — all missing. One message lists all.
        response = self._post_signup(client, "lower")
        assert b"more than 8" in response.data
        assert b"uppercase" in response.data
        assert b"special" in response.data

    def test_signup_form_shows_full_policy_in_help_text(self, client):
        response = client.get("/auth/signup")
        assert response.status_code == 200
        # The form-text under the password input lists every rule so the
        # user knows the policy before submitting.
        for token in (b"More than 8 characters",
                      b"uppercase",
                      b"lowercase",
                      b"special character"):
            assert token in response.data


class TestSignupOther:
    def test_signup_rejects_invalid_username_chars(self, client):
        response = client.post("/auth/signup", data={
            "username": "alice space",  # space is not allowed
            "email": "alice@example.com",
            "password": GOOD_PW, "confirm_password": GOOD_PW,
            "submit": "x",
        })
        assert b"Letters, numbers" in response.data


class TestLogin:
    def test_login_with_username(self, client, make_user, login):
        make_user("alice")
        response = login("alice")
        assert response.status_code == 200
        assert b"alice" in response.data

    def test_login_with_email_case_insensitive(self, client, make_user, login):
        make_user("alice", email="alice@example.com")
        response = login("ALICE@example.com")
        assert response.status_code == 200
        assert b"alice" in response.data

    def test_login_rejects_wrong_password(self, client, make_user, login):
        make_user("alice", password="CorrectPa55!")
        response = login("alice", password="WrongPa55!")
        assert b"Invalid username/email or password" in response.data

    def test_login_rejects_unknown_user(self, client, login):
        response = login("nobody")
        assert b"Invalid username/email or password" in response.data


class TestLogout:
    def test_logout_clears_session(self, client, make_user, login):
        make_user("alice")
        login("alice")
        # Confirm we're signed in.
        assert client.get("/dashboard/").status_code == 200
        client.post("/auth/logout")
        # Now anonymous — dashboard redirects to login.
        response = client.get("/dashboard/", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_logout_get_method_not_allowed(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/auth/logout")
        assert response.status_code == 405


class TestPasswordHashing:
    def test_check_password_round_trip(self):
        user = User(username="x", email="x@x.com")
        user.set_password("hunter22-correct-horse-battery-staple")
        assert user.check_password("hunter22-correct-horse-battery-staple")
        assert not user.check_password("anything-else")

    def test_set_password_uses_random_salt(self):
        """Two calls with the same plain text must produce different hashes."""
        a = User(username="a", email="a@a")
        b = User(username="b", email="b@b")
        a.set_password("same-password")
        b.set_password("same-password")
        assert a.password_hash != b.password_hash, \
            "hashes should differ — salt must be random per call"


class TestNextRedirectGuard:
    def test_relative_next_is_followed(self, client, make_user):
        make_user("alice")
        response = client.post(
            "/auth/login?next=/subjects/",
            data={"identifier": "alice", "password": "StrongPa55!", "submit": "x"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/subjects/")

    def test_absolute_next_is_rejected(self, client, make_user):
        make_user("alice")
        response = client.post(
            "/auth/login?next=https://evil.example/phish",
            data={"identifier": "alice", "password": "StrongPa55!", "submit": "x"},
            follow_redirects=False,
        )
        # The guard should drop the dangerous next= and use the default.
        assert "evil.example" not in response.headers.get("Location", "")
