# BracketEngine

Django web application for bracket/tournament management.

## Prerequisites

- Python 3.12+
- A virtual environment (`.venv` is already set up in this repo)

## Setup

1. Open a terminal in the project root (`BracketEngine`).

2. Activate the virtual environment:

   **PowerShell (Windows):**

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   **Command Prompt (Windows):**

   ```cmd
   .\.venv\Scripts\activate.bat
   ```

   **macOS / Linux:**

   ```bash
   source .venv/bin/activate
   ```

3. Install dependencies (first time only, or after pulling changes):

   ```bash
   pip install -r requirements.txt
   ```

4. Apply database migrations (first time only, or after model changes):

   ```bash
   python manage.py migrate
   ```

## Run the development server

With the virtual environment activated:

```bash
python manage.py runserver
```

The app will be available at:

- **Home:** http://127.0.0.1:8000/
- **Admin:** http://127.0.0.1:8000/admin/

To use a different host or port:

```bash
python manage.py runserver 0.0.0.0:8080
```

Press `Ctrl+C` in the terminal to stop the server.

## Optional: environment variables

Copy `.env.example` to `.env` and adjust values if needed. Settings read:

| Variable | Purpose |
|----------|---------|
| `DJANGO_SECRET_KEY` | Secret key (required in production) |
| `DJANGO_DEBUG` | `true` / `false` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts, e.g. `127.0.0.1,localhost` |

## Create an admin user

```bash
python manage.py createsuperuser
```

Then sign in at http://127.0.0.1:8000/admin/.
