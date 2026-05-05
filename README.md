# StudyPilot

A personal study-tracking web app that predicts how long your tasks will take, based on a model trained on your own past study sessions.

Built for the ITDS620 *Programming Languages and Software Development* summative assessment.

## Features

- **Tasks**: tag each task with subject, type, and complexity 1–5; add target words / pages where relevant.
- **Sessions**: log study time against a task; durations are summed into an "actual minutes" figure on completion.
- **Predictor (two layers)**:
  - A heuristic baseline using a per-type table from the spec (`Reading: 3 min × pages × (0.7 + 0.15c)` etc.).
  - A per-user Ridge regression that takes over after the user has 5+ completed tasks. Trained on every task completion, pickled to `instance/model_<user_id>.pkl`. Sanity-guarded: a regression prediction below the 15-minute floor or more than 3× the heuristic falls back to the heuristic.
- **Dashboard**: KPIs (hours total, hours this week, open tasks, done tasks), pie chart by subject, bar chart by day-of-week, due-soon table.
- **Smart planner**: distributes each open task's remaining minutes evenly across the days from today to its due date (next 14 days).
- **Insights**: streak, best study day, predicted-vs-actual scatter with `y=x` reference, signed-delta drift line, by-subject totals and averages.
- **Authentication**: Werkzeug password hashing, Flask-Login session management, CSRF on every POST. Every database query filters by `user_id == current_user.id`, and routes use `first_or_404()` so cross-user access is indistinguishable from a missing row.

## Status

**14 / 14 days complete.** All planned features shipped. See the day-by-day commit history for the staged build.

## Tech stack

- Python 3.11 (tested on 3.10), Flask 3
- SQLite via Flask-SQLAlchemy
- Flask-Login + Werkzeug for authentication
- Flask-WTF + WTForms (with `email-validator`) for forms and CSRF
- Bootstrap 5 (CDN) + Chart.js (CDN) for the front end
- scikit-learn + pandas + numpy for the regression predictor

## Setup

```bash
# 1. cd into the project
cd studypilot

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate            # macOS / Linux
# .\venv\Scripts\activate            # Windows PowerShell

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set SECRET_KEY to a long random string. Generate one with:
#   python -c "import secrets; print(secrets.token_hex(32))"

# 5. Initialise the database (creates tables and seeds the task type lookup)
flask --app app.py init-db

# 6. (Optional) Seed a demo user with 25 completed tasks across 4 subjects
flask --app app.py seed-demo
# Logs in as: demo / demo1234

# 7. Run the dev server
flask --app app.py run --debug
# Open http://127.0.0.1:5000
```

## Database schema

Five normalised tables plus a global `task_types` lookup. All foreign keys cascade where appropriate (deleting a user removes everything they own).

```
+--------+        +-----------+        +--------+
| users  |--<owns>| subjects  |<--FK---| tasks  |
|        |        |           |        |        |
| id PK  |        | id PK     |        | id PK  |
| user.. |        | user_id F |        | user_id F
| email  |        | name      |        | subject_id F
| pwhash |        | color     |        | type_id F ---> task_types
+--------+        +-----------+        | title       (id, name)
                                       | description
                                       | complexity
                                       | target_words
                                       | target_pages
                                       | predicted_minutes
                                       | due_date
                                       | status
                                       | completed_at
                                       +--------+
                                          |    |
                                          |    +---<has many>--- predictions
                                          |                       (id, task_id F,
                                          |                        predicted_minutes,
                                          |                        actual_minutes,
                                          |                        model_version,
                                          |                        created_at)
                                          |
                                          +---<has many>--- study_sessions
                                                             (id, user_id F, task_id F,
                                                              started_at, ended_at,
                                                              duration_minutes, note)
```

| Table | Purpose |
|---|---|
| `users` | accounts (Werkzeug-hashed password, unique username + email) |
| `subjects` | per-user subject list, unique-by-(user_id, name), with hex colour |
| `task_types` | global lookup seeded with Reading, Essay, Problem Set, Coding, Revision, Other |
| `tasks` | the work the user is tracking |
| `study_sessions` | logged time against a task; summed into `predictions.actual_minutes` on completion |
| `predictions` | one row per task, written on save with the predictor's estimate; `actual_minutes` and `model_version` make this the audit trail for prediction accuracy |

## Project structure

```
studypilot/
├── app.py                          entry point: flask --app app.py run --debug
├── config.py                       Config class — SECRET_KEY, DATABASE_URL from env
├── requirements.txt
├── .env.example
├── README.md
├── REPORT.md                       written report for the assignment
├── instance/                       SQLite db + per-user model pickles (gitignored)
└── studypilot/
    ├── __init__.py                 create_app factory + init-db / seed-demo CLI
    ├── extensions.py               db, login_manager, csrf singletons
    ├── models.py                   User, Subject, TaskType, Task, StudySession, Prediction
    ├── auth/                       /auth/signup, /auth/login, /auth/logout
    ├── subjects/                   /subjects CRUD
    ├── tasks/                      /tasks CRUD + status transitions
    ├── sessions/                   /sessions/task/<id>/new, /sessions/<id>/delete
    ├── dashboard/                  /dashboard
    ├── planner/                    /planner — two-week distribution
    ├── insights/                   /insights — accuracy charts and streak
    ├── ml/                         predictor.py, features.py, trainer.py
    ├── templates/                  base.html + per-blueprint subfolders
    └── static/css/style.css
```

## Architecture notes

- **Blueprint per feature.** Each top-level URL prefix (`auth/`, `tasks/`, `subjects/`, `sessions/`, `dashboard/`, `planner/`, `insights/`) lives in its own package with `__init__.py`, `routes.py`, and (where needed) `forms.py`. Models stay shared in `studypilot/models.py`.
- **Ownership pattern.** Every protected route is `@login_required`; every query that touches user data starts with `.filter_by(user_id=current_user.id)`; ID-based lookups use `first_or_404()` so attempts to access another user's row return the same 404 as a missing row.
- **Predictor staging.** `predict_minutes(task, user)` is the only public entry point. Internally it tries the user's pickled regression first (loaded lazily; sklearn isn't imported until needed), falls back to the heuristic on any failure, sanity-guards the result, and clamps to `[15 min, 12 h]`.
- **Templates.** All pages extend `base.html`; the navbar uses Bootstrap's collapsible pattern (hamburger on small screens) and switches the right-hand menu on `current_user.is_authenticated`.

## Code style

Docstrings on every public function and class; inline comments explain the *why* of non-obvious choices (handle_unknown="ignore" on the encoder, the `slots` key rename in the planner, the `"yesterday or today"` anchor in the streak counter). Run `ruff check .` if you want a lint pass — clean as of Day 13.
