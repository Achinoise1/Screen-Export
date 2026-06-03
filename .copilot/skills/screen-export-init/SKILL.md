---
name: screen-export-init
description: "Init skill for Screen-Export project. Sets up Python .venv, installs deps, and starts the FastAPI backend. Modes: init (default, full setup + run), install only (setup without starting server), run only (start existing venv server), deploy (show deployment instructions for nginx sub-website)."
argument-hint: "init (default) | install only | run only | deploy"
---

# screen-export-init Skill

Automates environment setup and server startup for the Screen-Export project.

## Project Context

| Item | Value |
|---|---|
| Runtime | Python 3.11 |
| Virtualenv | `.venv` (project root) |
| Dependencies | `requirements.txt` |
| Server entry | `backend/main.py` |
| Default port | `8001` (overridable via `BACKEND_PORT` env) |
| Data dir | `./data/` (auto-created on first run) |

> **Note**: `main.py` at the repo root is a legacy standalone script — it is NOT the web server.

---

## Mode: `init` (default)

Full setup from scratch. Run when the project is freshly cloned or the environment is missing.

**Step 1 — Check existing venv**

```bash
ls .venv/bin/python 2>/dev/null && echo "exists" || echo "missing"
```

If `.venv` already exists and has a working Python binary, skip to Step 3.

**Step 2 — Create `.venv`**

`python3.11-venv` may not be installed on the system; use the `--without-pip` workaround and bootstrap pip manually.

```bash
python3 -m venv .venv --without-pip
curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
.venv/bin/python3 /tmp/get-pip.py
rm /tmp/get-pip.py
```

Report: "✅ .venv created and pip bootstrapped"

**Step 3 — Install dependencies**

```bash
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Report: "✅ Dependencies installed"

**Step 4 — Start server (background)**

```bash
nohup .venv/bin/python backend/main.py > /tmp/screen-export.log 2>&1 &
echo $! > /tmp/screen-export.pid
```

Wait 3 seconds for startup.

**Step 5 — Verify**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/
```

- If response is `200`: report "✅ Server is running at http://localhost:8001/"
- If not: show last 20 lines of `/tmp/screen-export.log` and report the error

---

## Mode: `install only`

Create `.venv` and install dependencies without starting the server. Use when preparing a deployment environment or CI.

Execute **Steps 1–3** from `init` mode, then stop.

Report: "✅ Environment ready. Run `.venv/bin/python backend/main.py` to start the server."

---

## Mode: `run only`

Assume `.venv` already exists. Just start the server.

**Step 1 — Check venv exists**

```bash
ls .venv/bin/python 2>/dev/null || echo "ERROR: .venv not found — run 'screen-export-init' first"
```

If `.venv` is missing, abort and tell the user to run `init` mode first.

**Step 2 — Check if server is already running**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/ 2>/dev/null
```

If `200`, report "ℹ️ Server is already running at http://localhost:8001/" and stop.

**Step 3 — Start server**

Execute **Step 4** from `init` mode, then verify with **Step 5**.

---

## Stopping the Server

To stop the background server:

```bash
kill $(cat /tmp/screen-export.pid) 2>/dev/null && echo "Server stopped"
```

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `BACKEND_PORT` | `8001` | Change the listening port |
| `SCREENSHOT_EXPORT_DATA_DIR` | `./data` | Relocate the data directory |
| `BACKEND_ROOT_PATH` | `` | Nginx sub-path prefix (set for sub-website deploy) |

---

## Mode: `deploy`

Show the steps to deploy Screen-Export as a sub-website under an existing nginx static site.

**Target sub-path**: `/tools/screenshot-export`  
**Deploy files**: already prepared in the `deploy/` directory of the repo.

**Step 1 — Copy project to deploy server**

```bash
# On deploy server — adjust path as needed
git clone <repo-url> /opt/screen-export
cd /opt/screen-export
```

**Step 2 — Set up the environment on the deploy server**

Run `screen-export-init install only` (or manually):
```bash
python3 -m venv .venv --without-pip
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3
.venv/bin/pip install -r requirements.txt
```

**Step 3 — Install the systemd service**

```bash
# Edit User= and WorkingDirectory= in the file first if needed
sudo cp deploy/screen-export.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable screen-export
sudo systemctl start screen-export
```

Verify the backend is up:
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/
# Expected: 200
```

**Step 4 — Add nginx location block**

Open your nginx server config (e.g. `/etc/nginx/sites-enabled/yoursite`) and paste
the contents of `deploy/nginx-snippet.conf` inside the `server { ... }` block,
**before** any catch-all `location /` block.

```bash
sudo nginx -t && sudo systemctl reload nginx
```

**Step 5 — Verify end-to-end**

```bash
curl -s -o /dev/null -w "%{http_code}" https://yoursite.com/tools/screenshot-export/
# Expected: 200
```

Open `https://yoursite.com/tools/screenshot-export/` in a browser — the upload UI should appear.

---

### Key files reference

| File | Purpose |
|---|---|
| `deploy/screen-export.service` | Systemd unit template |
| `deploy/nginx-snippet.conf` | Nginx location block to paste into server config |
