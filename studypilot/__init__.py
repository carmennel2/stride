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
    # auth.login route is added on Day 2 — naming it now is harmless.
    login_manager.login_view = "auth.login"

    # Register blueprints. More will be added on Days 3-11.
    from studypilot.auth.routes import bp as auth_bp
    from studypilot.main.routes import bp as main_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)

    # CLI commands.
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create all database tables. Run once after installing."""
        # Import models so SQLAlchemy registers them on db.metadata before
        # create_all() runs — otherwise tables defined in unimported modules
        # would be silently skipped.
        import studypilot.models  # noqa: F401

        with app.app_context():
            db.create_all()
        click.echo("Database initialised at instance/studypilot.db")

    return app
