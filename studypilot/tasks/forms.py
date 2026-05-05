"""WTForms classes for the tasks blueprint."""
from datetime import date

from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from studypilot.models import Subject, TaskType


class TaskForm(FlaskForm):
    """Create or edit a task.

    Subject and type choices are populated from the DB at instantiation
    time so the dropdowns reflect what the current user actually has.
    target_words / target_pages are conditionally required based on the
    chosen task type — see `validate_*` below.
    """

    title = StringField(
        "Title",
        validators=[DataRequired(), Length(min=1, max=120)],
    )
    description = TextAreaField(
        "Description",
        validators=[Optional(), Length(max=2000)],
    )
    subject_id = SelectField("Subject", coerce=int, validators=[DataRequired()])
    type_id = SelectField("Type", coerce=int, validators=[DataRequired()])
    complexity = SelectField(
        "Complexity",
        coerce=int,
        choices=[(i, f"{i} — " + label) for i, label in enumerate(
            ["", "very easy", "easy", "moderate", "hard", "very hard"]
        ) if i >= 1],
        default=3,
    )
    target_words = IntegerField(
        "Target words (essays)",
        validators=[Optional(), NumberRange(min=1, max=100_000)],
    )
    target_pages = IntegerField(
        "Target pages (reading)",
        validators=[Optional(), NumberRange(min=1, max=10_000)],
    )
    due_date = DateField(
        "Due date",
        validators=[DataRequired()],
        default=date.today,
    )
    submit = SubmitField("Save")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Choices are dynamic — must be set per-request, after the user
        # is known and per the current state of the DB.
        self.subject_id.choices = [
            (s.id, s.name)
            for s in Subject.query.filter_by(user_id=current_user.id)
            .order_by(Subject.name)
        ]
        self.type_id.choices = [
            (t.id, t.name) for t in TaskType.query.order_by(TaskType.id)
        ]

    def validate_subject_id(self, field: SelectField) -> None:
        """Reject subject IDs that aren't on the current user's list.

        SelectField already enforces the value is in self.choices, but
        defending here too means a forged POST can't sneak a foreign
        subject_id past us.
        """
        owned_ids = {sid for sid, _ in self.subject_id.choices}
        if field.data not in owned_ids:
            raise ValidationError("Pick one of your own subjects.")

    def validate(self, extra_validators=None) -> bool:
        """Run base validators, then enforce target_words/target_pages by type.

        Has to live at form level because target_words/target_pages use
        Optional(), which short-circuits before per-field validate_<x>
        hooks would run when the field is empty.
        """
        ok = super().validate(extra_validators=extra_validators)
        type_name = self._selected_type_name()
        if type_name == "Essay" and not self.target_words.data:
            self.target_words.errors.append("Essays need a target word count.")
            ok = False
        if type_name == "Reading" and not self.target_pages.data:
            self.target_pages.errors.append("Reading tasks need a target page count.")
            ok = False
        return ok

    def _selected_type_name(self) -> str | None:
        """Look up the chosen type's name. None if no/invalid selection."""
        if not self.type_id.data:
            return None
        tt = TaskType.query.get(self.type_id.data)
        return tt.name if tt else None
