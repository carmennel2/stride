"""WTForms classes for the auth blueprint.

Validators run server-side on every submission, so we don't trust the
browser's `required` attribute. Flask-WTF also wires up CSRF protection
automatically as long as SECRET_KEY is set.
"""
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Regexp,
    ValidationError,
)

from studypilot.models import User


class SignupForm(FlaskForm):
    """New-account form. Uniqueness is enforced both here and at the DB level."""

    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=64),
            # Keep usernames URL-safe and predictable.
            Regexp(
                r"^[A-Za-z0-9_.-]+$",
                message="Letters, numbers, dots, dashes and underscores only.",
            ),
        ],
    )
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=120)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128)],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Create account")

    # WTForms calls validate_<field> automatically during form.validate().
    def validate_username(self, field: StringField) -> None:
        """Reject usernames already taken by another account."""
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("That username is already taken.")

    def validate_email(self, field: StringField) -> None:
        """Reject emails already taken by another account."""
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError("An account with that email already exists.")


class LoginForm(FlaskForm):
    """Returning-user form. Accepts either username or email in one field."""

    identifier = StringField(
        "Username or email",
        validators=[DataRequired(), Length(max=120)],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Log in")
