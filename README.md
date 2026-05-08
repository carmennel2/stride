# Stride

A personal study-tracking web app that predicts how long your tasks will take, based on a model trained on your own past study sessions.

Built for the ITDS620 *Programming Languages and Software Development* summative assessment.

**Live demo:** https://carmennel.pythonanywhere.com/ (sign in as `demo` / `Demo1234!`)

## Features

- **Tasks**: tag each task with subject, type, and complexity 1–5; add target words / pages where relevant.
- **Sessions**: log study time against a task; durations are summed into an "actual minutes" figure on completion.
- **Predictor (two layers)**:
  - A heuristic baseline using a per-type table (`Reading: 3 min × pages × (0.7 + 0.15c)` etc.).
  - A per-user Ridge regression that takes over after the user has 5+ completed tasks. Trained on every task completion, pickled to `instance/model_<user_id>.pkl`. Sanity-guarded: a regression prediction below the 15-minute floor or more than 3× the heuristic falls back to the heuristic.
- **Dashboard**: KPIs (hours total, hours this week, open tasks, done tasks), pie chart by subject, bar chart by day-of-week, due-soon table.
- **Smart planner**: distributes each open task's remaining minutes evenly across the days from today to its due date (next 14 days).
- **Calendar**: month grid with tasks shown on their due dates, coloured by subject.
- **Insights**: streak, best study day, predicted-vs-actual scatter with `y=x` reference, signed-delta drift line, by-subject totals and averages.
- **Authentication**: Werkzeug password hashing, Flask-Login session management, CSRF on every POST. Every database query filters by `user_id == current_user.id`, and routes use `first_or_404()` so cross-user access is indistinguishable from a missing row. Session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` in production.
- **Google sign-in (optional)**: federated login alongside username/password. Uses Authlib for OpenID Connect; a separate `oauth_identities` table maps `(provider, provider_user_id)` to a `User`.

## Tech stack

- Python 3.11 (tested on 3.10), Flask 3
- SQLite via Flask-SQLAlchemy
- Flask-Login + Werkzeug for authentication; Authlib for OAuth
- Flask-WTF + WTForms (with `email-validator`) for forms and CSRF
- Bootstrap 5 (CDN) + Chart.js (CDN) for the front end
- scikit-learn + pandas + numpy for the regression predictor

## Setup

```bash
# 1. cd into the project
cd stride

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

# 6. (Optional) Seed a demo user with the project's modules and a populated history
flask --app app.py seed-demo
# Logs in as: demo / Demo1234!

# 7. Run the dev server
flask --app app.py run --debug
# Open http://127.0.0.1:5000
```

## Database schema

Six user-scoped tables plus a global `task_types` lookup. All foreign keys cascade where appropriate.

```mermaid
erDiagram
    users ||--o{ oauth_identities : has
    users ||--o{ subjects : owns
    users ||--o{ tasks : owns
    users ||--o{ study_sessions : owns
    subjects ||--o{ tasks : "groups"
    task_types ||--o{ tasks : "categorises"
    tasks ||--o{ predictions : "scored by"
    tasks ||--o{ study_sessions : "tracked by"

    users {
        int id PK
        string username UK
        string email UK
        string password_hash "nullable for OAuth-only"
        datetime created_at
    }
    oauth_identities {
        int id PK
        int user_id FK
        string provider
        string provider_user_id
        string email
        datetime created_at
    }
    subjects {
        int id PK
        int user_id FK
        string name
        string color "#rrggbb"
        datetime created_at
    }
    task_types {
        int id PK
        string name UK
    }
    tasks {
        int id PK
        int user_id FK
        int subject_id FK
        int type_id FK
        string title
        text description
        int complexity "1-5"
        int target_words "nullable"
        int target_pages "nullable"
        int predicted_minutes
        date due_date
        string status
        datetime created_at
        datetime completed_at "nullable"
    }
    study_sessions {
        int id PK
        int user_id FK
        int task_id FK
        datetime started_at
        datetime ended_at
        int duration_minutes
        string note
    }
    predictions {
        int id PK
        int task_id FK
        int predicted_minutes
        int actual_minutes "nullable until done"
        string model_version
        datetime created_at
    }
```

| Table | Purpose |
|---|---|
| `users` | accounts (Werkzeug-hashed password, nullable for OAuth-only users; unique username + email) |
| `oauth_identities` | links a user to one external identity at an OAuth provider (currently Google); unique on (provider, provider_user_id) |
| `subjects` | per-user subject list, unique-by-(user_id, name), with hex colour |
| `task_types` | global lookup seeded with Reading, Essay, Problem Set, Coding, Revision, Other |
| `tasks` | the work the user is tracking |
| `study_sessions` | logged time against a task; summed into `predictions.actual_minutes` on completion |
| `predictions` | one row per task, written on save with the predictor's estimate; `actual_minutes` and `model_version` make this the audit trail for prediction accuracy |

## Project structure

```
stride/
├── app.py                  entry point: flask --app app.py run --debug
├── config.py               Config + TestConfig
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml          ruff config
├── pytest.ini
├── .env.example
├── README.md
├── REPORT.md               written report for the assignment
├── instance/               SQLite db + per-user model pickles (gitignored)
├── tests/                  pytest suite against in-memory SQLite
└── stride/
    ├── __init__.py         create_app factory + init-db / seed-demo CLI
    ├── extensions.py       db, login_manager, csrf, oauth singletons
    ├── models.py           User, OAuthIdentity, Subject, TaskType, Task, StudySession, Prediction
    ├── auth/               /auth/signup, /auth/login, /auth/logout, /auth/oauth/google/*
    ├── subjects/           /subjects CRUD
    ├── tasks/              /tasks CRUD + status transitions
    ├── sessions/           /sessions/task/<id>/new, /sessions/<id>/delete
    ├── dashboard/          /dashboard
    ├── planner/            /planner — two-week distribution
    ├── calendar/           /calendar — monthly grid
    ├── insights/           /insights — accuracy charts and streak
    ├── account/            /account — profile + password + linked accounts
    ├── ml/                 predictor.py, features.py, trainer.py
    ├── templates/          base.html + per-blueprint subfolders + errors/
    └── static/css/style.css
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

The suite uses an in-memory SQLite database via the `TestConfig`, so each test
gets a clean schema. Run-time: under 10 seconds.
