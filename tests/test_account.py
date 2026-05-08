"""Account settings tests."""
from __future__ import annotations

from stride.models import OAuthIdentity, User


class TestAccountIndex:
    def test_anonymous_redirects_to_login(self, client):
        response = client.get("/account/", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_authenticated_renders(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.get("/account/")
        assert response.status_code == 200
        assert b"Account settings" in response.data
        assert b"alice" in response.data


class TestChangePassword:
    def test_user_with_password_must_supply_current(
        self, client, make_user, login, db
    ):
        make_user("alice", password="OldPass123!")
        login("alice", password="OldPass123!")
        response = client.post("/account/password", data={
            "current_password": "WrongOldPass!",
            "new_password": "NewPass123!",
            "confirm_new_password": "NewPass123!",
            "submit": "x",
        }, follow_redirects=True)
        assert b"doesn&#39;t match your current password" in response.data \
            or b"doesn't match" in response.data

        # Old password still works.
        user = User.query.filter_by(username="alice").one()
        assert user.check_password("OldPass123!")
        assert not user.check_password("NewPass123!")

    def test_change_with_correct_current(self, client, make_user, login):
        make_user("alice", password="OldPass123!")
        login("alice", password="OldPass123!")
        response = client.post("/account/password", data={
            "current_password": "OldPass123!",
            "new_password": "NewPass456!",
            "confirm_new_password": "NewPass456!",
            "submit": "x",
        }, follow_redirects=True)
        assert b"Password updated" in response.data

        user = User.query.filter_by(username="alice").one()
        assert user.check_password("NewPass456!")
        assert not user.check_password("OldPass123!")

    def test_oauth_only_user_can_set_first_password(self, client, db):
        user = User(username="ogonly", email="o@gmail.com", password_hash=None)
        db.session.add(user)
        db.session.commit()
        # Log in via the user_loader (simulate post-OAuth state).
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        response = client.post("/account/password", data={
            "new_password": "FirstPass1!",
            "confirm_new_password": "FirstPass1!",
            "submit": "x",
        }, follow_redirects=True)
        assert b"Password updated" in response.data

        refreshed = User.query.get(user.id)
        assert refreshed.password_hash is not None
        assert refreshed.check_password("FirstPass1!")

    def test_weak_new_password_rejected(self, client, make_user, login):
        make_user("alice", password="OldPass123!")
        login("alice", password="OldPass123!")
        response = client.post("/account/password", data={
            "current_password": "OldPass123!",
            "new_password": "weak",
            "confirm_new_password": "weak",
            "submit": "x",
        }, follow_redirects=True)
        # Form-level validation message is flashed.
        assert b"more than 8" in response.data or b"Password needs" in response.data


class TestUnlinkProvider:
    def test_unlinks_provider(self, client, make_user, login, db):
        user = make_user("alice", password="Pass1234!")
        db.session.add(OAuthIdentity(
            user_id=user.id, provider="google",
            provider_user_id="g-1", email="alice@gmail.com",
        ))
        db.session.commit()

        login("alice", password="Pass1234!")
        response = client.post("/account/unlink/google", follow_redirects=True)
        assert b"Google unlinked" in response.data
        assert OAuthIdentity.query.filter_by(provider="google").count() == 0

    def test_cannot_unlink_only_signin_method(self, client, db):
        # OAuth-only user with one linked provider.
        user = User(username="ogonly", email="o@gmail.com", password_hash=None)
        db.session.add(user)
        db.session.flush()
        db.session.add(OAuthIdentity(
            user_id=user.id, provider="google",
            provider_user_id="g-1", email="o@gmail.com",
        ))
        db.session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        response = client.post("/account/unlink/google", follow_redirects=True)
        assert b"only sign-in method" in response.data
        # Identity still attached.
        assert OAuthIdentity.query.filter_by(provider="google").count() == 1

    def test_unknown_provider_404(self, client, make_user, login):
        make_user("alice")
        login("alice")
        response = client.post("/account/unlink/dropbox")
        assert response.status_code == 404


class TestDeleteAccount:
    def test_deletes_with_correct_password(self, client, make_user, login):
        make_user("alice", password="Pass1234!")
        login("alice", password="Pass1234!")
        response = client.post("/account/delete", data={
            "confirm": "Pass1234!", "submit": "x",
        }, follow_redirects=True)
        assert b"account has been deleted" in response.data
        assert User.query.filter_by(username="alice").count() == 0

    def test_wrong_password_does_not_delete(self, client, make_user, login):
        make_user("alice", password="Pass1234!")
        login("alice", password="Pass1234!")
        response = client.post("/account/delete", data={
            "confirm": "WrongPass!", "submit": "x",
        }, follow_redirects=True)
        assert b"doesn&#39;t match" in response.data or b"doesn't match" in response.data
        assert User.query.filter_by(username="alice").count() == 1

    def test_oauth_only_user_must_type_delete(self, client, db):
        user = User(username="ogonly", email="o@gmail.com", password_hash=None)
        db.session.add(user)
        db.session.commit()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        # Wrong confirmation word.
        response = client.post("/account/delete", data={
            "confirm": "yes", "submit": "x",
        }, follow_redirects=True)
        assert b"Type &#39;delete&#39;" in response.data \
            or b"Type 'delete'" in response.data
        assert User.query.count() == 1

        # Correct confirmation.
        response = client.post("/account/delete", data={
            "confirm": "delete", "submit": "x",
        }, follow_redirects=True)
        assert b"account has been deleted" in response.data
        assert User.query.count() == 0
