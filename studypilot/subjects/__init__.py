"""Subjects blueprint.

CRUD for the user's study subjects. Every query in this blueprint is
filtered by `user_id == current_user.id` — see routes.py for the
ownership pattern.
"""
