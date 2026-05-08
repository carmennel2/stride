"""Session form."""
from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError


class StudySessionForm(FlaskForm):
    started_at = DateTimeLocalField(
        "Started",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired(message="Please enter when the session started.")],
    )
    ended_at = DateTimeLocalField(
        "Ended",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired(message="Please enter when the session ended.")],
    )
    note = StringField(
        "Note (optional)",
        validators=[
            Optional(),
            Length(max=500, message="Note must be 500 characters or fewer."),
        ],
    )
    submit = SubmitField("Log session")

    def validate_ended_at(self, field: DateTimeLocalField) -> None:
        if not self.started_at.data or not field.data:
            return
        if field.data <= self.started_at.data:
            raise ValidationError("End time must be after start time.")
        delta = field.data - self.started_at.data
        if delta.total_seconds() > 24 * 3600:
            raise ValidationError("A single session can't span more than 24 hours.")
