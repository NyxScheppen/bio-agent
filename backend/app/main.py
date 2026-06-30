from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.chat import router as chat_router
from app.api.upload import router as upload_router
from app.api.history import router as history_router
from app.api.system import router as system_router

from app.core.paths import STORAGE_DIR, GENERATED_DIR
from app.db.database import Base, engine

# =========================
# 基础路径
# main.py 位于 backend/app/main.py
# 所以：
# APP_DIR     = backend/app
# BACKEND_DIR = backend
# STATIC_DIR  = backend/static
# =========================
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
STATIC_DIR = BACKEND_DIR / "static"
ASSETS_DIR = STATIC_DIR / "assets"
INDEX_HTML = STATIC_DIR / "index.html"

print("APP_DIR =", APP_DIR)
print("BACKEND_DIR =", BACKEND_DIR)
print("STATIC_DIR =", STATIC_DIR)
print("STATIC exists =", STATIC_DIR.exists())
print("ASSETS_DIR =", ASSETS_DIR)
print("ASSETS exists =", ASSETS_DIR.exists())
print("INDEX_HTML =", INDEX_HTML)
print("INDEX_HTML exists =", INDEX_HTML.exists())

print("STORAGE_DIR =", STORAGE_DIR)
print("GENERATED_DIR =", GENERATED_DIR)
print("STORAGE exists =", os.path.exists(str(STORAGE_DIR)))
print("GENERATED exists =", os.path.exists(str(GENERATED_DIR)))

# 自动建表
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bio Agent Backend")

# 允许前端跨域访问

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not STORAGE_DIR.exists():
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/files", StaticFiles(directory=str(STORAGE_DIR)), name="files")


app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(history_router)
app.include_router(system_router)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "message": "Bio Agent Backend is running",
        "static_dir": str(STATIC_DIR),
        "static_exists": STATIC_DIR.exists(),
        "assets_dir": str(ASSETS_DIR),
        "assets_exists": ASSETS_DIR.exists(),
        "index_html": str(INDEX_HTML),
        "index_exists": INDEX_HTML.exists(),
        "storage_dir": str(STORAGE_DIR),
        "storage_exists": STORAGE_DIR.exists(),
        "generated_dir": str(GENERATED_DIR),
        "generated_exists": GENERATED_DIR.exists(),
    }


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/")
async def serve_index():
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML))

    return {
        "message": "Bio Agent Backend is running",
        "warning": f"Frontend index.html not found: {INDEX_HTML}",
    }


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    normalized = full_path.strip("/")

    if (
        normalized.startswith("api/")
        or normalized == "api"
        or normalized.startswith("files/")
        or normalized == "files"
        or normalized.startswith("assets/")
        or normalized == "assets"
    ):
        raise HTTPException(status_code=404, detail="Not Found")

    if not STATIC_DIR.exists() or not INDEX_HTML.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Frontend static directory or index.html not found: {STATIC_DIR}",
        )

    target = STATIC_DIR / normalized

    # 如果请求的是 static 下真实存在的文件，比如 favicon.svg、robots.txt
    if target.exists() and target.is_file():
        return FileResponse(str(target))

    # React/Vite SPA 路由兜底
    return FileResponse(str(INDEX_HTML))