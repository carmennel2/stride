"""StudyPilot application factory.

The factory pattern lets us create multiple app instances with different
configurations (useful for testing) and keeps imports flexible.
"""
from pathlib import Path

import click
from flask import Flask

from config import Config
from studypilot.extensions import csrf, db, login_manager


def create_app(config_class: type[Config] = Config) -> Flask:
    """Create and configure a Flask application instance.

    Args:
        config_class: A Config subclass. Defaults to the base Config.

    Returns:
        A fully configured Flask app, ready to run.
    """
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)

    # SQLite needs the instance/ folder to exist before it can write to it.
    Path(app.root_path).parent.joinpath("instance").mkdir(exist_ok=True)

    # Initialise extensions against this app instance.
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Make `today` available in every template — saves passing it from
    # every route that wants to colour-code due dates.
    from datetime import date

    @app.context_processor
    def inject_today() -> dict:
        return {"today": date.today()}

    # Custom error pages. 404 covers both genuinely-missing pages and the
    # "not yours" first_or_404() responses used throughout the app.
    from flask import render_template

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        # 500 means an unhandled exception — db state may be inconsistent.
        # Roll back so subsequent requests on this connection don't see
        # the half-written transaction.
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403
    # auth.login route is added on Day 2 — naming it now is harmless.
    login_manager.login_view = "auth.login"

    # Register blueprints.
    from studypilot.auth.routes import bp as auth_bp
    from studypilot.dashboard.routes import bp as dashboard_bp
    from studypilot.insights.routes import bp as insights_bp
    from studypilot.main.routes import bp as main_bp
    from studypilot.planner.routes import bp as planner_bp
    from studypilot.sessions.routes import bp as sessions_bp
    from studypilot.subjects.routes import bp as subjects_bp
    from studypilot.tasks.routes import bp as tasks_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(subjects_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(planner_bp)

    # CLI commands.
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create all database tables and seed lookup data.

        Safe to re-run: create_all() skips tables that already exist and
        seed_task_types() only inserts categories that aren't there yet.
        """
        # Import models so SQLAlchemy registers them on db.metadata before
        # create_all() runs — otherwise tables defined in unimported modules
        # would be silently skipped.
        import studypilot.models  # noqa: F401
        from studypilot.models import seed_task_types

        with app.app_context():
            db.create_all()
            added = seed_task_types()
        click.echo("Database initialised at instance/studypilot.db")
        if added:
            click.echo(f"Seeded {added} task type(s).")

    return app
