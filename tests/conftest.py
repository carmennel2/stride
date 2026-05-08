"""Pytest fixtures."""
from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from config import TestConfig
from stride import create_app
from stride.extensions import db as _db
from stride.models import Subject, User, seed_task_types


@pytest.fixture(scope="session")
def app() -> Iterator[Flask]:
    # tempdir for instance_path keeps model pickles out of the real tree.
    with tempfile.TemporaryDirectory() as instance_dir:
        flask_app = create_app(TestConfig, instance_path=instance_dir)
        with flask_app.app_context():
            yield flask_app


@pytest.fixture(autouse=True)
def _purge_model_pickles(app: Flask) -> Iterator[None]:
    yield
    instance = Path(app.instance_path)
    if instance.exists():
        for pkl in instance.glob("model_*.pkl"):
            pkl.unlink()


@pytest.fixture(autouse=True)
def _reset_db(app: Flask) -> Iterator[None]:
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        seed_task_types()
        yield
        _db.session.rollback()


@pytest.fixture()
def db(app: Flask):
    return _db


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture()
def make_user(app: Flask):
    def _factory(
        username: str = "alice",
        email: str | None = None,
        password: str = "StrongPa55!",
    ) -> User:
        email = email or f"{username}@example.com"
        user = User(username=username, email=email)
        user.set_password(password)
        _db.session.add(user)
        _db.session.commit()
        return user

    return _factory


@pytest.fixture()
def make_subject(app: Flask):
    def _factory(
        user: User,
        name: str = "Maths",
        color: str = "#10b981",
    ) -> Subject:
        subj = Subject(user_id=user.id, name=name, color=color)
        _db.session.add(subj)
        _db.session.commit()
        return subj

    return _factory


@pytest.fixture()
def login(client: FlaskClient):
    def _login(username: str, password: str = "StrongPa55!"):
        return client.post(
            "/auth/login",
            data={"identifier": username, "password": password, "submit": "x"},
            follow_redirects=True,
        )

    return _login
