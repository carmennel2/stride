"""Subject form."""
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, ValidationError

from stride.models import Subject


class SubjectForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[
            DataRequired(message="Please give the subject a name."),
            Length(min=1, max=80, message="Subject name must be 80 characters or fewer."),
        ],
    )
    color = StringField(
        "Colour",
        validators=[
            DataRequired(message="Please pick a colour."),
            Regexp(
                r"^#[0-9A-Fa-f]{6}$",
                message="Use a hex colour like #336699.",
            ),
        ],
        default="#10b981",
    )
    submit = SubmitField("Save")

    def __init__(self, *args, original_name: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.original_name = original_name

    def validate_name(self, field: StringField) -> None:
        # An unchanged name on edit shouldn't trip the uniqueness check.
        if self.original_name is not None and field.data == self.original_name:
            return

        clash = Subject.query.filter_by(
            user_id=current_user.id, name=field.data
        ).first()
        if clash is not None:
            raise ValidationError("You already have a subject with that name.")
