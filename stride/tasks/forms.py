"""Task form."""
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

from stride.models import Subject, TaskType


class TaskForm(FlaskForm):
    title = StringField(
        "Title",
        validators=[
            DataRequired(message="Please give the task a title."),
            Length(min=1, max=120, message="Title must be 120 characters or fewer."),
        ],
    )
    description = TextAreaField(
        "Description",
        validators=[
            Optional(),
            Length(max=2000, message="Description must be 2000 characters or fewer."),
        ],
    )
    subject_id = SelectField(
        "Subject", coerce=int,
        validators=[DataRequired(message="Please choose a subject.")],
    )
    type_id = SelectField(
        "Type", coerce=int,
        validators=[DataRequired(message="Please choose a task type.")],
    )
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
        validators=[
            Optional(),
            NumberRange(min=1, max=100_000,
                        message="Target words should be between 1 and 100,000."),
        ],
    )
    target_pages = IntegerField(
        "Target pages (reading)",
        validators=[
            Optional(),
            NumberRange(min=1, max=10_000,
                        message="Target pages should be between 1 and 10,000."),
        ],
    )
    due_date = DateField(
        "Due date",
        validators=[DataRequired(message="Please pick a due date.")],
        default=date.today,
    )
    submit = SubmitField("Save")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Dynamic per-request: dropdowns reflect this user's current data.
        self.subject_id.choices = [
            (s.id, s.name)
            for s in Subject.query.filter_by(user_id=current_user.id)
            .order_by(Subject.name)
        ]
        self.type_id.choices = [
            (t.id, t.name) for t in TaskType.query.order_by(TaskType.id)
        ]

    def validate_subject_id(self, field: SelectField) -> None:
        # Defence-in-depth: a forged POST could include a subject_id outside
        # this user's list. Reject before the FK constraint would catch it.
        owned_ids = {sid for sid, _ in self.subject_id.choices}
        if field.data not in owned_ids:
            raise ValidationError("Pick one of your own subjects.")

    def validate(self, extra_validators=None) -> bool:
        # Form-level rather than per-field: target_words/target_pages use
        # Optional(), which short-circuits per-field hooks when empty.
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
        if not self.type_id.data:
            return None
        tt = TaskType.query.get(self.type_id.data)
        return tt.name if tt else None
