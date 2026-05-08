"""Stride application factory."""
from pathlib import Path

import click
from flask import Flask

from config import Config
from stride.extensions import csrf, db, limiter, login_manager, oauth, rate_limit_response


def create_app(
    config_class: type[Config] = Config,
    *,
    instance_path: str | None = None,
) -> Flask:
    """Create and configure a Flask app instance."""
    if instance_path is None:
        instance_path = str(Path(__file__).resolve().parent.parent / "instance")
    app = Flask(__name__, instance_relative_config=False, instance_path=instance_path)
    app.config.from_object(config_class)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    # "strong" rotates the session when IP/User-Agent changes mid-session.
    login_manager.session_protection = app.config.get(
        "SESSION_PROTECTION", "strong"
    )
    csrf.init_app(app)
    oauth.init_app(app)
    limiter.init_app(app)
    _register_oauth_providers(app)

    from datetime import date

    @app.context_processor
    def inject_today() -> dict:
        return {"today": date.today()}

    from flask import render_template

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        # Roll back so the next request doesn't see a half-written transaction.
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(400)
    def bad_request(error):
        reason = getattr(error, "description", None) or str(error)
        return render_template("errors/400.html", reason=reason), 400

    @app.errorhandler(401)
    def unauthorised(_error):
        return render_template("errors/401.html"), 401

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return render_template("errors/405.html"), 405

    app.register_error_handler(429, rate_limit_response)

    from stride.account.routes import bp as account_bp
    from stride.auth.oauth import bp as oauth_bp
    from stride.auth.routes import bp as auth_bp
    from stride.calendar.routes import bp as calendar_bp
    from stride.dashboard.routes import bp as dashboard_bp
    from stride.insights.routes import bp as insights_bp
    from stride.main.routes import bp as main_bp
    from stride.planner.routes import bp as planner_bp
    from stride.sessions.routes import bp as sessions_bp
    from stride.subjects.routes import bp as subjects_bp
    from stride.tasks.routes import bp as tasks_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(oauth_bp)
    app.register_blueprint(subjects_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(account_bp)

    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        """Populate a 'demo' account with realistic data."""
        from stride.demo_seed import seed_demo

        with app.app_context():
            summary = seed_demo()
        click.echo("Demo user seeded:")
        for k, v in summary.items():
            click.echo(f"  {k}: {v}")

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create all DB tables and seed lookup data."""
        # Importing models so SQLAlchemy sees their tables before create_all().
        import stride.models  # noqa: F401
        from stride.models import seed_task_types

        with app.app_context():
            db.create_all()
            added = seed_task_types()
        click.echo("Database initialised at instance/stride.db")
        if added:
            click.echo(f"Seeded {added} task type(s).")

    return app


def _register_oauth_providers(app: Flask) -> None:
    """Register OAuth clients for providers that have credentials set."""
    configured: list[str] = []

    if app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url=(
                "https://accounts.google.com/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": "openid email profile"},
        )
        configured.append("google")

    from stride.auth.oauth import PROVIDERS as _ALL_OAUTH_PROVIDERS

    @app.context_processor
    def inject_oauth_providers() -> dict:
        return {
            "oauth_providers": _ALL_OAUTH_PROVIDERS,
            "configured_oauth_providers": tuple(configured),
        }
