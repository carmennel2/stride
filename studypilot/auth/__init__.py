"""Authentication blueprint.

Owns signup, login, and logout — everything that decides whether a request
belongs to a known user. The actual route handlers live in routes.py and
the WTForms classes in forms.py.
"""
