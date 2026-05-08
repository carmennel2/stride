"""Auth forms."""
import re

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

from stride.models import User

PASSWORD_MIN_LENGTH = 9
PASSWORD_MAX_LENGTH = 128
PASSWORD_HELP_TEXT = (
    f"More than {PASSWORD_MIN_LENGTH - 1} characters, "
    "with an uppercase letter, a lowercase letter, and a special character."
)


def strong_password(_form, field) -> None:
    """Reject passwords missing length, upper, lower, or special chars."""
    pw = field.data or ""
    failures: list[str] = []
    if len(pw) < PASSWORD_MIN_LENGTH:
        failures.append(f"more than {PASSWORD_MIN_LENGTH - 1} characters")
    if not re.search(r"[A-Z]", pw):
        failures.append("an uppercase letter")
    if not re.search(r"[a-z]", pw):
        failures.append("a lowercase letter")
    if not re.search(r"[^A-Za-z0-9]", pw):
        failures.append("a special character")
    if failures:
        raise ValidationError("Password needs: " + ", ".join(failures) + ".")


class SignupForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Please choose a username."),
            Length(
                min=3, max=64,
                message="Username should be between 3 and 64 characters.",
            ),
            Regexp(
                r"^[A-Za-z0-9_.-]+$",
                message="Letters, numbers, dots, dashes and underscores only.",
            ),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Please enter your email address."),
            Email(message="That doesn't look like a valid email address."),
            Length(max=120, message="Email is too long."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Please choose a password."),
            Length(
                max=PASSWORD_MAX_LENGTH,
                message=f"Password is too long (max {PASSWORD_MAX_LENGTH} characters).",
            ),
            strong_password,
        ],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(message="Please re-enter your password to confirm."),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Create account")

    def validate_username(self, field: StringField) -> None:
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("That username is already taken.")

    def validate_email(self, field: StringField) -> None:
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError("An account with that email already exists.")


class LoginForm(FlaskForm):
    identifier = StringField(
        "Username or email",
        validators=[
            DataRequired(message="Please enter your username or email."),
            Length(max=120),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Please enter your password.")],
    )
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Log in")
