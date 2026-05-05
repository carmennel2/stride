"""Planner blueprint.

Distributes the user's outstanding work across the next two weeks. Each
pending or in-progress task contributes a slice of its remaining
predicted minutes to every day from today through its due date.
"""
