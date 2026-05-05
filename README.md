# StudyPilot

A personal study-tracking web app that predicts how long your tasks will take, based on a model trained on your own past study sessions.

Built for the ITDS620 *Programming Languages and Software Development* summative assessment.

## Features (planned)

- Add tasks tagged by subject, type, and complexity
- Log study sessions against tasks
- Time predictor — heuristic baseline + Ridge regression that learns from your history
- Dashboard with hours by subject and day
- Smart planner that distributes outstanding work across remaining days
- Insights page: prediction accuracy, best study day, average pace by subject
- Authentication and per-user data isolation

## Status

**Day 1 of 14 — scaffold complete.** The app boots, the landing page renders, and the database can be initialised. Auth lands on Day 2.

## Tech stack

- Python 3.11, Flask 3
- SQLite via Flask-SQLAlchemy
- Flask-Login + Werkzeug for authentication
- Flask-WTF + WTForms for forms and CSRF
- Bootstrap 5 (CDN) + Chart.js (CDN) for the front end
- scikit-learn, pandas, numpy for the predictor

## Setup

```bash
# 1. Clone or unzip the project, then cd into it
cd studypilot

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate            # macOS / Linux
# .\venv\Scripts\activate            # Windows PowerShell

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and set SECRET_KEY to a long random string.

# 5. Initialise the database
flask --app app.py init-db

# 6. Run the dev server
flask --app app.py run --debug
# Open http://127.0.0.1:5000 in your browser.
```

## Project structure

```
studypilot/
├── app.py                  # entry point
├── config.py               # Config class
├── requirements.txt
├── .env.example
├── README.md
├── instance/               # SQLite db lives here (gitignored)
└── studypilot/             # application package
    ├── __init__.py         # create_app factory
    ├── extensions.py       # db, login_manager singletons
    ├── main/               # landing page + dashboard blueprint
    ├── templates/
    └── static/
```

Auth (`auth/`), tasks (`tasks/`), sessions (`sessions/`), planner (`planner/`), insights (`insights/`), and the ML module (`ml/`) will be added on later days.

## Day-by-day roadmap

See `studypilot_plan.md` in the project root for the full plan.

| Day | Focus |
|---|---|
| 1 | Project skeleton, app factory, hello-world page |
| 2 | User model, signup/login/logout, hashed passwords |
| 3 | Subjects + task type lookup, ownership filters |
| 4 | Tasks CRUD + heuristic predictor stub |
| 5 | Study sessions, actual-minutes rollup |
| 6 | Dashboard v1 with charts |
| 7 | Buffer + heuristic predictor proper |
| 8 | Regression model + retraining hook |
| 9 | Predicted vs actual everywhere |
| 10 | Smart planner |
| 11 | Insights page |
| 12 | Responsive polish + validation + error pages |
| 13 | Comments, README, code cleanup |
| 14 | Demo data, final report, submit |
