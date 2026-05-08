"""Account settings forms."""
from flask_wtf import FlaskForm
from wtforms import PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length

from stride.auth.forms import PASSWORD_MAX_LENGTH, strong_password


class ChangePasswordForm(FlaskForm):
    # Optional in the field sense — required only when the user already
    # has a local password (OAuth-only accounts setting one for the
    # first time skip this).
    current_password = PasswordField("Current password")
    new_password = PasswordField(
        "New password",
        validators=[
            DataRequired(message="Please choose a password."),
            Length(
                max=PASSWORD_MAX_LENGTH,
                message=f"Password is too long (max {PASSWORD_MAX_LENGTH} characters).",
            ),
            strong_password,
        ],
    )
    confirm_new_password = PasswordField(
        "Confirm new password",
        validators=[
            DataRequired(message="Please re-enter the new password."),
            EqualTo("new_password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Change password")


class DeleteAccountForm(FlaskForm):
    confirm = PasswordField(
        "Password",
        validators=[DataRequired(message="Enter your password to confirm.")],
    )
    submit = SubmitField("Delete my account")
