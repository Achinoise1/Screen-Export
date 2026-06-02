import os
from pathlib import Path

# ── 端口 ──────────────────────────────────────────────
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8001"))
FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", "8002"))

# ── 子路径（nginx proxy_pass 挂载点）─────────────────
# 本地开发留空；部署到 nginx 子路径时通过环境变量设置：
#   export BACKEND_ROOT_PATH=/screen-export/api
#   export FRONTEND_ROOT_PATH=/screen-export
BACKEND_ROOT_PATH: str = os.getenv("BACKEND_ROOT_PATH", "")
FRONTEND_ROOT_PATH: str = os.getenv("FRONTEND_ROOT_PATH", "")

# ── 数据目录 ──────────────────────────────────────────
BASE_DIR: Path = Path(__file__).parent
DATA_DIR: Path = BASE_DIR / "data"

UPLOAD_DIR: Path = DATA_DIR / "uploads"
SCREENSHOTS_DIR: Path = DATA_DIR / "screenshots"
OUTPUTS_DIR: Path = DATA_DIR / "outputs"

for _d in (UPLOAD_DIR, SCREENSHOTS_DIR, OUTPUTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── API 地址（前端访问后端用）────────────────────────
# 开发环境直连；生产环境走 nginx 子路径
API_BASE_URL: str = f"http://localhost:{BACKEND_PORT}"
