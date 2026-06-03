---
name: screenshot-export-init
description: "Init skill for Screenshot-Export project. Sets up Python .venv, installs deps, and starts the FastAPI backend. Modes: init (default, full setup + run), install only (setup without starting server), run only (start existing venv server), deploy (run deploy.zsh for production — use '--init' for first-time deploy, default for updates)."
argument-hint: "init (default) | install only | run only | deploy [--init]"
---

# screenshot-export-init Skill

Automates environment setup and server startup for the Screenshot-Export project.

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
nohup .venv/bin/python backend/main.py > /tmp/screenshot-export.log 2>&1 &
echo $! > /tmp/screenshot-export.pid
```

Wait 3 seconds for startup.

**Step 5 — Verify**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/
```

- If response is `200`: report "✅ Server is running at http://localhost:8001/"
- If not: show last 20 lines of `/tmp/screenshot-export.log` and report the error

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
ls .venv/bin/python 2>/dev/null || echo "ERROR: .venv not found — run 'screenshot-export-init' first"
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
kill $(cat /tmp/screenshot-export.pid) 2>/dev/null && echo "Server stopped"
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

Deploy Screenshot-Export to the production server using `deploy.zsh`.

### Configuration (top of `deploy.zsh`)

| Variable | Value | Purpose |
|---|---|---|
| `REMOTE` | `server` | SSH host alias for the deploy target |
| `REMOTE_DIR` | `/data/projs/Screenshot-Export` | Project root on the server |
| `DATA_DIR` | `/var/screenshot-export-data` | Persistent data directory (must match `SCREENSHOT_EXPORT_DATA_DIR` in the systemd service) |

---

### First-time deploy: `--init`

Run from the repo root:

```zsh
./deploy.zsh --init
```

What it does:

1. **Package** — `tar czf package.tar.gz backend/ deploy/ frontend/ config.py requirements.txt`
2. **Transfer** — `scp package.tar.gz server:/tmp/` then removes the local tarball
3. **Remote dir** — `mkdir -p $REMOTE_DIR`, extract tarball, `chown -R www-data:www-data`
4. **Data dir** — `mkdir -p $DATA_DIR && chown -R www-data:www-data $DATA_DIR`
5. **Python 3.11** — installs via `deadsnakes` PPA, creates `.venv`, installs `requirements.txt`
6. **Nginx** — copies `deploy/nginx-snippet.conf` to `/etc/nginx/snippets/screenshot-export/`, runs `nginx -t && rlnginx`
7. **Systemd** — copies `deploy/screenshot-export.service` to `/etc/systemd/system/`, runs `sysdr && systemctl enable --now screenshot-export.service`

> **Shell aliases used on server**: `rlnginx` (reload nginx), `sysdr` (systemctl daemon-reload), `rstse` (restart screenshot-export service).

---

### Update deploy (default)

```zsh
./deploy.zsh
```

What it does:

1. **Package & Transfer** — same as above
2. **Extract** — unpacks tarball into existing `$REMOTE_DIR`, `chown -R www-data:www-data`
3. **Restart service** — runs `rstse` on the server

---

### Automatic rollback on error

If the script exits with an error, the `cleanup` trap runs automatically:

- Removes any local `package.tar.gz` and remote `/tmp/package.tar.gz`
- In `--init` mode only: rolls back the systemd service, nginx snippet, and remote directory if they were created in that run

---

### Key files reference

| File | Purpose |
|---|---|
| `deploy.zsh` | Main deploy script (run from repo root) |
| `deploy/screenshot-export.service` | Systemd unit template |
| `deploy/nginx-snippet.conf` | Nginx snippet copied to `/etc/nginx/snippets/screenshot-export/` |
