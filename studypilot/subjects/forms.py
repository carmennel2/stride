"""WTForms classes for the subjects blueprint."""
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, ValidationError

from studypilot.models import Subject


class SubjectForm(FlaskForm):
    """Create or edit a study subject.

    Used by both /subjects/new and /subjects/<id>/edit. Pass the existing
    name as `original_name` when editing so the uniqueness check ignores
    the row being updated.
    """

    name = StringField(
        "Name",
        validators=[DataRequired(), Length(min=1, max=80)],
    )
    color = StringField(
        "Colour",
        # HTML5 colour pickers always produce #rrggbb, but a stray paste
        # could include something else — validate just in case.
        validators=[
            DataRequired(),
            Regexp(
                r"^#[0-9A-Fa-f]{6}$",
                message="Use a hex colour like #336699.",
            ),
        ],
        default="#3366ff",
    )
    submit = SubmitField("Save")

    def __init__(self, *args, original_name: str | None = None, **kwargs) -> None:
        """Track the pre-edit name so uniqueness validation can ignore self."""
        super().__init__(*args, **kwargs)
        self.original_name = original_name

    def validate_name(self, field: StringField) -> None:
        """Reject duplicate subject names within the same user."""
        # On edit, an unchanged name shouldn't trip the uniqueness check.
        if self.original_name is not None and field.data == self.original_name:
            return

        clash = Subject.query.filter_by(
            user_id=current_user.id, name=field.data
        ).first()
        if clash is not None:
            raise ValidationError("You already have a subject with that name.")
