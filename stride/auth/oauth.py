"""OAuth sign-in for Google, Microsoft, and Facebook."""
from __future__ import annotations

import logging
import re
from typing import Any

from flask import Blueprint, abort, flash, redirect, url_for
from flask_login import current_user, login_user

from stride.extensions import db, oauth
from stride.models import OAuthIdentity, User

bp = Blueprint("oauth", __name__, url_prefix="/auth/oauth")
logger = logging.getLogger(__name__)


PROVIDERS = ("google", "microsoft", "facebook")
PROVIDER_LABELS = {
    "google": "Google",
    "microsoft": "Microsoft",
    "facebook": "Facebook",
}


def _provider_or_404(name: str):
    """Return the OAuth client, or 404 for unknown providers.

    Returns None when the provider is known but its credentials aren't
    configured; callers handle that with a flash + redirect.
    """
    if name not in PROVIDERS:
        abort(404)
    return oauth.create_client(name)


def _setup_flash(provider: str):
    label = PROVIDER_LABELS[provider]
    flash(
        f"Sign in with {label} isn't available right now. "
        "Please use your email and password, or try a different provider.",
        "warning",
    )
    return redirect(url_for("auth.login"))


def _userinfo_from_google(token: dict[str, Any]) -> dict[str, Any]:
    info = token.get("userinfo") or {}
    return {
        "provider_user_id": info.get("sub"),
        "email": (info.get("email") or "").lower() or None,
        "name": info.get("name"),
    }


def _userinfo_from_microsoft(token: dict[str, Any]) -> dict[str, Any]:
    info = token.get("userinfo") or {}
    # Microsoft sometimes uses preferred_username instead of email.
    email = info.get("email") or info.get("preferred_username") or ""
    return {
        "provider_user_id": info.get("sub"),
        "email": email.lower() or None,
        "name": info.get("name"),
    }


def _userinfo_from_facebook(client, token: dict[str, Any]) -> dict[str, Any]:
    response = client.get("me?fields=id,name,email", token=token)
    info = response.json() if response is not None else {}
    return {
        "provider_user_id": info.get("id"),
        "email": (info.get("email") or "").lower() or None,
        "name": info.get("name"),
    }


def _username_from(name: str | None, email: str | None) -> str:
    """Sanitise a display name into a unique username."""
    base = name or (email or "user").split("@", 1)[0]
    base = re.sub(r"[^A-Za-z0-9_.-]", "", base) or "user"
    base = base[:60]  # leave room for a _NN suffix under the 64 cap

    if not User.query.filter_by(username=base).first():
        return base

    suffix = 2
    while True:
        candidate = f"{base}_{suffix}"
        if not User.query.filter_by(username=candidate).first():
            return candidate
        suffix += 1


def _login_with(provider: str, info: dict[str, Any]):
    sub = info.get("provider_user_id")
    email = info.get("email")
    name = info.get("name")

    if not sub:
        flash(
            f"{PROVIDER_LABELS[provider]} sign-in failed: no account "
            "identifier returned.",
            "danger",
        )
        return redirect(url_for("auth.login"))

    identity = OAuthIdentity.query.filter_by(
        provider=provider, provider_user_id=str(sub)
    ).first()
    if identity is not None:
        login_user(identity.user)
        flash(f"Welcome back, {identity.user.username}.", "success")
        return redirect(url_for("main.index"))

    # Link to an existing email account before creating a fresh one.
    user = User.query.filter_by(email=email).first() if email else None
    created = False
    if user is None:
        if not email:
            flash(
                f"{PROVIDER_LABELS[provider]} did not share an email "
                "address with us; can't create an account.",
                "warning",
            )
            return redirect(url_for("auth.login"))
        user = User(
            username=_username_from(name, email),
            email=email,
            password_hash=None,
        )
        db.session.add(user)
        db.session.flush()
        created = True

    db.session.add(OAuthIdentity(
        user_id=user.id,
        provider=provider,
        provider_user_id=str(sub),
        email=email,
    ))
    db.session.commit()

    login_user(user)
    if created:
        flash(
            f"Account created via {PROVIDER_LABELS[provider]} — welcome, "
            f"{user.username}.",
            "success",
        )
    else:
        flash(
            f"Linked {PROVIDER_LABELS[provider]} to your existing account.",
            "success",
        )
    return redirect(url_for("main.index"))


@bp.route("/<string:provider>/login")
def oauth_login(provider: str):
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    client = _provider_or_404(provider)
    if client is None:
        return _setup_flash(provider)
    redirect_uri = url_for("oauth.oauth_callback", provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


@bp.route("/<string:provider>/callback")
def oauth_callback(provider: str):
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    client = _provider_or_404(provider)
    if client is None:
        return _setup_flash(provider)

    try:
        token = client.authorize_access_token()
    except Exception:  # noqa: BLE001
        logger.exception("OAuth token exchange failed for %s", provider)
        flash(
            f"Sign-in with {PROVIDER_LABELS.get(provider, provider)} failed. "
            "Please try again.",
            "danger",
        )
        return redirect(url_for("auth.login"))

    if provider == "google":
        info = _userinfo_from_google(token)
    elif provider == "microsoft":
        info = _userinfo_from_microsoft(token)
    elif provider == "facebook":
        info = _userinfo_from_facebook(client, token)
    else:
        abort(404)

    return _login_with(provider, info)
