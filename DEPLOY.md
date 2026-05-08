# Deployment guide

Two paths below. PythonAnywhere is the recommended path for assignment
submission: free, no credit card, HTTPS by default, well-documented
Flask support. Render.com is the alternative if you'd rather have
auto-deploy on `git push`.

---

## Option A — PythonAnywhere (recommended)

### 1. Sign up

Create a Beginner (free) account at https://www.pythonanywhere.com.

### 2. Open a Bash console

From the dashboard, click **Consoles → Bash**.

### 3. Clone the repository

```bash
cd ~
git clone https://github.com/<your-username>/stride.git
cd stride
```

### 4. Create a virtualenv with Python 3.10

```bash
mkvirtualenv --python=python3.10 stride-venv
pip install -r requirements.txt
```

### 5. Create the database and seed task types

```bash
flask --app app.py init-db
flask --app app.py seed-demo
```

### 6. Configure the web app

From the dashboard, click **Web → Add a new web app**:

1. Choose **Manual configuration → Python 3.10**.
2. On the configuration page, edit these fields:

   - **Source code**: `/home/<your-username>/stride`
   - **Working directory**: `/home/<your-username>/stride`
   - **Virtualenv**: `/home/<your-username>/.virtualenvs/stride-venv`

3. Click **WSGI configuration file** and replace its contents with:

   ```python
   import sys
   from pathlib import Path

   project = Path("/home/<your-username>/stride")
   if str(project) not in sys.path:
       sys.path.insert(0, str(project))

   from dotenv import load_dotenv
   load_dotenv(project / ".env")

   from stride import create_app
   application = create_app()
   ```

### 7. Set environment variables

In the **Web** tab, scroll to **Environment variables** and add:

- `SECRET_KEY` — generate with
  `python -c "import secrets; print(secrets.token_hex(32))"`
- `FLASK_ENV` — `production` (so session cookies become `Secure`)
- (Optional) Any of the OAuth client id/secret pairs you've registered.

### 8. Reload

Click the green **Reload** button. Your app is live at
`https://<your-username>.pythonanywhere.com/`.

### 9. (Optional) Google OAuth callback

If you set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in step 7, add
the production callback URL to the list of "Authorised redirect URIs"
in your Google Cloud OAuth client:

- `https://<your-username>.pythonanywhere.com/auth/oauth/google/callback`

---

## Option B — Render.com

Render auto-deploys from GitHub. Useful if you want every `git push`
to redeploy.

### 1. Push the repository to GitHub.

### 2. On https://render.com, click **New → Web Service** and connect the repo.

### 3. Configuration

- **Runtime**: Python 3
- **Build command**: `pip install -r requirements.txt`
- **Start command**:
  `gunicorn --workers 2 --bind 0.0.0.0:$PORT "stride:create_app()"`

### 4. Add environment variables (Settings → Environment):

- `SECRET_KEY` (generate as above)
- `FLASK_ENV` — `production`
- (Optional) OAuth credentials.

### 5. Click **Create Web Service**.

The free tier sleeps after 15 minutes of inactivity, so the first
request after a quiet period takes ~30 seconds while the container
spins up. Subsequent requests are normal speed.

---

## Updating the running site

PythonAnywhere: `git pull` in the bash console, then **Reload** in the
Web tab.

Render: `git push origin main` and wait for the auto-deploy.

---

## Sanity check

Once deployed, visit the live URL and confirm:

- [ ] Landing page loads.
- [ ] Sign up creates a new account.
- [ ] Demo login works (`demo` / `Demo1234!`) if you ran `seed-demo`.
- [ ] Dashboard, Tasks, Subjects, Planner, and Insights all render.
- [ ] HTTPS is active (no padlock warnings).
- [ ] The session cookie carries the `Secure` and `HttpOnly` flags
  (visible in the browser's dev tools → Application → Cookies).
