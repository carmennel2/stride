"""WTForms classes for the sessions blueprint."""
from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError


class StudySessionForm(FlaskForm):
    """Log a study session against a task.

    started_at and ended_at use HTML5 datetime-local inputs, so the form
    sees them as naive local-time datetimes — that's fine for a
    single-user assignment, and matches what the user would type.
    """

    started_at = DateTimeLocalField(
        "Started",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()],
    )
    ended_at = DateTimeLocalField(
        "Ended",
        format="%Y-%m-%dT%H:%M",
        validators=[DataRequired()],
    )
    note = StringField(
        "Note (optional)",
        validators=[Optional(), Length(max=500)],
    )
    submit = SubmitField("Log session")

    def validate_ended_at(self, field: DateTimeLocalField) -> None:
        """End must be after start, and the session can't be 24h+ long."""
        if not self.started_at.data or not field.data:
            return
        if field.data <= self.started_at.data:
            raise ValidationError("End time must be after start time.")
        delta = field.data - self.started_at.data
        if delta.total_seconds() > 24 * 3600:
            raise ValidationError("A single session can't span more than 24 hours.")
