# StudyPilot — ITDS620 Project Report

## 1. Introduction

StudyPilot is a personal study-tracking web application I built for the ITDS620 *Programming Languages and Software Development* assessment. The brief asked for a working web application with at least three pages, persistent storage, user authentication, and a recognisable software-engineering structure. I chose a single, focused use case: a tool a student can use to plan their study time, log how long they actually spend on tasks, and have the application learn from that history to give increasingly accurate time estimates for future work.

The user-facing flow is: register, add a few subjects, add the tasks you need to complete, log study sessions against them as you work, and mark each one done when finished. As the database fills up with completed tasks, the application's predictions for new tasks shift from a generic heuristic to a model trained on the user's own habits. The dashboard, planner, and insights pages turn that data into something readable.

This report describes how the application is structured, how the predictor works, how authentication and authorisation are enforced, and the design choices I'd revisit if I had longer.

## 2. Functional overview

The application has six pages once a user is logged in:

- **Dashboard** — KPI cards (hours total, hours this week, open tasks, completed tasks), a pie chart of hours by subject, a bar chart of hours per weekday, and a "due in the next seven days" table.
- **Tasks** — list with status filter pills (all / pending / in progress / done) and an actual-vs-predicted column for completed tasks.
- **Task detail** — full description, status controls, the prediction card with the model version that produced it, a session-logging form, and the per-task session log.
- **Subjects** — full CRUD with per-user uniqueness, a hex colour for charts.
- **Planner** — fifteen rows (today plus the next fourteen days) showing how much time the user should spend on each open task each day. Today is highlighted.
- **Insights** — current streak, best study weekday, mean absolute error, signed bias, predicted-vs-actual scatter, signed-delta drift line, by-subject totals.

Plus the auth pages (signup, login) and a public landing page that redirects to the dashboard for logged-in users.

## 3. Architecture

The application uses Flask's *blueprint per feature area* pattern. There is no monolithic `views.py`; each functional area lives in its own package with its own routes, forms, and (where relevant) URL prefix:

```
studypilot/
├── auth/        /auth/*
├── subjects/    /subjects/*
├── tasks/       /tasks/*
├── sessions/    /sessions/*
├── dashboard/   /dashboard/
├── planner/     /planner/
├── insights/    /insights/
└── ml/          predictor.py, features.py, trainer.py
```

Models are shared in `studypilot/models.py` so blueprints don't need to import each other for the schema. Cross-cutting concerns (the `db`, the `LoginManager`, the `CSRFProtect`) are singletons in `studypilot/extensions.py`, kept separate from the app factory in `studypilot/__init__.py` to avoid circular imports.

The application factory pattern (`create_app(config_class=Config)`) is what registers blueprints, initialises extensions, and wires error handlers and template context processors. This is the recommended Flask layout because it makes the app testable: another instance with a different config can be created without reaching into module-level globals.

For the user interface I used Bootstrap 5 (loaded from CDN) for layout and Chart.js (also CDN) for the dashboard and insights charts. Bootstrap's grid handles responsive design automatically; the navbar uses the collapsible hamburger pattern below the `lg` breakpoint, and tables are wrapped in `table-responsive` so they scroll horizontally rather than overflowing on narrow viewports.

## 4. Database design

The schema has five normalised tables plus a global `task_types` lookup, all with foreign keys cascading from `users`:

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id`, `username`, `email`, `password_hash`, `created_at` | unique on username and email |
| `subjects` | `id`, `user_id`, `name`, `color`, `created_at` | unique on `(user_id, name)` |
| `task_types` | `id`, `name` | global lookup, seeded on `init-db` |
| `tasks` | `id`, `user_id`, `subject_id`, `type_id`, `title`, `description`, `complexity`, `target_words`, `target_pages`, `predicted_minutes`, `due_date`, `status`, `created_at`, `completed_at` | nullable size hints, status in `{pending, in_progress, done}` |
| `study_sessions` | `id`, `user_id`, `task_id`, `started_at`, `ended_at`, `duration_minutes`, `note` | duration is denormalised for fast aggregation |
| `predictions` | `id`, `task_id`, `predicted_minutes`, `actual_minutes`, `model_version`, `created_at` | one row per task, written on save and updated when the task is completed |

There are a few decisions worth highlighting. Subject names are unique *per user*, not globally — two students can both have a "Maths" subject without conflict. `task_types` is a global lookup with a fixed seed list because the predictor uses type as a categorical feature, and I want consistent categories so the model is comparable across users. Both `target_words` and `target_pages` are nullable: Reading uses pages, Essay uses words, the other types use neither, and forcing zeroes everywhere would have made the schema lie. The `predictions` table stores `model_version` so the insights page can compare heuristic and regression accuracy on the same chart.

I chose to denormalise `duration_minutes` on `study_sessions` even though it can be computed from `(ended_at - started_at)`. The dashboard sums durations on every page render; doing the arithmetic at read-time across hundreds of sessions adds latency that storing one extra integer avoids.

## 5. Authentication and authorisation

The auth side is straightforward: passwords are hashed with `werkzeug.security.generate_password_hash` (Werkzeug 3 defaults to scrypt), sessions are managed by Flask-Login, and CSRF tokens are issued by Flask-WTF (with `CSRFProtect` covering bare-POST endpoints like `/auth/logout` that don't go through a `FlaskForm`). The signup and login forms use `DataRequired`, `Length`, `Email`, `EqualTo`, and a `Regexp` validator on usernames; uniqueness is enforced at both the WTForms level (`validate_username`, `validate_email`) and the database level (unique columns) so the app degrades gracefully under a race.

Authorisation is the half of the auth criterion students often miss. Every protected route in StudyPilot has the `@login_required` decorator, but more importantly, **every database query that touches user data starts with `.filter_by(user_id=current_user.id)`**. ID-based lookups use `first_or_404()`, so an attempt to access another user's task or subject by ID returns the same 404 response as a non-existent ID. There is no leak of whether the row exists; the application doesn't even need a 403 path for ownership violations because we never let one happen.

I also defended against forged form submissions where the client could attempt to attach a foreign `subject_id` to a task. The `TaskForm` populates the subject dropdown from the user's own subjects per request, and a server-side `validate_subject_id` rejects anything outside that set even before the foreign-key constraint would fire. Open-redirect attacks on the post-login `?next=` parameter are blocked by a small helper that only accepts relative URLs.

## 6. The predictor

The prediction layer is the most interesting piece of engineering. The public entry point is `predict_minutes(task, user)` in `studypilot/ml/predictor.py`, which returns `(minutes, model_version)`. Internally there are two strategies stacked behind sanity guards.

**Heuristic baseline.** A small table from the spec, encoded directly:

| Type | Base | Scaling |
|---|---|---|
| Reading | 3 min × pages | × (0.7 + 0.15 × complexity) |
| Essay | 30 min × (target_words / 100) | × (0.7 + 0.15 × complexity) |
| Problem Set | 60 min | × complexity |
| Coding | 90 min | × complexity |
| Revision | 45 min | × complexity |
| Other | 60 min | × complexity |

The heuristic is bounded by a 15-minute floor and a 12-hour cap. It works for a brand-new account immediately and never produces nonsense.

**Per-user Ridge regression.** Once a user has 5 or more completed tasks with logged sessions, `train_model_for_user()` fits a scikit-learn `Pipeline` consisting of a `ColumnTransformer` (one-hot encoding `subject_id` and `type_id`, passing numeric features through) and `Ridge(alpha=1.0)`. The features are `subject_id`, `type_id`, `complexity`, `target_words`, `target_pages`, `description_word_count`, and `days_until_due`; the target is `actual_minutes` summed from the task's logged sessions. The fitted pipeline is pickled to `instance/model_<user_id>.pkl` so each user has their own model — there is no shared training set, and one user's data never influences another's predictions.

The regression is trained on every task completion, hooked from the task status route inside a `try/except` that swallows training failures so the user flow is never blocked by a sklearn hiccup. Since training sets are small (tens to a few hundred rows) the fit runs in milliseconds.

**Sanity guards.** A regression fitted on a few dozen rows can produce wild predictions on inputs unlike anything it was trained on — a brand-new subject with no comparable history, or a complexity-5 essay when the user has only ever written complexity-3 essays. I addressed this with three guards on the predict path:

1. If the regression returns NaN or infinity, fall back.
2. If the prediction is below the 15-minute floor, fall back.
3. If the prediction is more than three times the heuristic, fall back.

Any of those falls back to the heuristic, and the resulting `model_version` reflects which predictor actually answered. This is what lets the insights page truthfully show how often each predictor is firing.

The `OneHotEncoder` is configured with `handle_unknown="ignore"`, so even a brand-new subject ID at predict time produces an all-zero categorical row instead of crashing — less accurate than retraining, but harmless. Sklearn imports are deferred until the regression path actually runs, so the heuristic-only request that happens before a user has any data doesn't pull in pandas, numpy, and sklearn during startup.

I chose Ridge over plain ordinary-least-squares because regularisation matters more than feature engineering when the training set is small. With 5–25 rows there is real risk of overfitting noise; the L2 penalty pulls coefficients toward zero unless the data argues otherwise. I considered tree models (a small `RandomForestRegressor`) but decided the explainability of a linear model — and the speed of fitting it on every completion — were the better trade-offs at this size.

## 7. UI/UX choices

I tried to keep the interface dense without being overwhelming. Each page is laid out as a row of small KPI cards at the top, the main visualisation in the middle, and supporting tables or lists below. Subject colour is the consistent through-line: the user picks a hex colour when creating a subject, and that colour shows up on the dashboard pie, the task list dot, the planner badges, and the insights table. It's a small detail but it makes the app feel coherent.

Empty states get explicit treatment. A brand-new user signing up sees a clearly-labelled "no sessions logged yet" message on every chart instead of an empty axis or a cryptic zero. This matters a lot in an assessment context — the marker is going to log in, click around, and form an opinion about polish in the first thirty seconds.

For forms, every error renders with Bootstrap's `is-invalid` class and an `invalid-feedback` block beneath the field, instead of as a global alert. That makes correcting a multi-error submission much faster.

## 8. What I'd do differently

A few things I'd revisit with more time:

- **Aggregations.** The dashboard, planner, and insights routes pull all of a user's sessions into Python and aggregate there, rather than using SQL `GROUP BY`. This is fine for an assignment-scale dataset, but past a few thousand sessions it would start to bite. A real refactor would push the aggregations into queries.
- **Session timezones.** Study sessions are stored as naive datetimes — the assumption is that the user is logging local time and viewing local time, with no jet lag. A real product would store UTC and render in the browser's timezone.
- **Predictor evaluation.** I trust the sanity guards but I don't have automated tests that show the regression is actually beating the heuristic on a realistic dataset. The seed-demo CLI exists partly so I could eyeball the difference, but a proper cross-validated comparison would be the right thing.
- **Tests.** I wrote scratch smoke-tests in the terminal as I built each day's feature, but I didn't promote them to a pytest suite. The architecture supports it cleanly — `_build_plan` in the planner is already a pure function, the predictor is decoupled from Flask, and the form validators are unit-testable in isolation.
- **Concurrent-edit safety.** SQLite plus a single-writer Flask dev server means there are no real concurrency hazards in practice, but the model uses no version columns or optimistic locking. A move to Postgres would invite reconsidering that.

## 9. Conclusion

Building StudyPilot taught me a lot about how the small architectural decisions compound: choosing the blueprint pattern early made every subsequent feature easy to slot in; the ownership pattern (`filter_by(user_id=current_user.id)` on every query plus `first_or_404()` for ID lookups) is a genuinely small amount of code that buys complete data isolation; staging the predictor as heuristic-then-regression-with-fallback meant the product was usable from the very first task, not after the user had laboriously created twenty so the model had something to learn from.

I committed in fourteen daily increments mirroring the project plan, ran `ruff` clean across the codebase, and seeded a demonstration account (`demo` / `demo1234`) so the marker can see all the features populated with realistic data via `flask seed-demo`. The code lives in `studypilot/` with comments where the *why* of a decision is non-obvious, and a `README.md` that documents setup, schema, and architecture.

The application meets the brief, and I'd happily keep using it.
