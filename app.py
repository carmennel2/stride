"""Application entry point.

Run with:
    flask --app app.py run --debug

Or, equivalently:
    python app.py
"""
from dotenv import load_dotenv

# Load environment variables from .env BEFORE importing the app factory so
# Config picks them up.
load_dotenv()

from stride import create_app  # noqa: E402  (import after load_dotenv)

app = create_app()


if __name__ == "__main__":
    # Convenience for `python app.py`. Production would use a WSGI server.
    app.run(debug=True)
