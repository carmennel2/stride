"""Tasks blueprint.

CRUD for the user's tracked study tasks plus the status transitions
(pending -> in_progress -> done). Predicted minutes are filled in on
creation by `studypilot.ml.predictor`. Day 5 adds the session-logging
form on the detail page.
"""
