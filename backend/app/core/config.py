import os
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# 大模型配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")

# 服务配置
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", 8000))

# CORS 允许的来源（逗号分隔）。生产环境前端由 FastAPI 同源提供，无需跨域；
# 默认仅放行本机 Vite 开发服务器。定位为本地单用户工具，禁止使用 "*"。
_cors_raw = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _positive_int_env(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


# Upload and preview resource budgets. Values are bytes unless otherwise noted.
MAX_UPLOAD_FILES = _positive_int_env("MAX_UPLOAD_FILES", 20, 1000)
MAX_UPLOAD_FILE_BYTES = _positive_int_env(
    "MAX_UPLOAD_FILE_BYTES", 100 * 1024 * 1024, 10 * 1024 * 1024 * 1024
)
MAX_UPLOAD_BATCH_BYTES = _positive_int_env(
    "MAX_UPLOAD_BATCH_BYTES", 250 * 1024 * 1024, 20 * 1024 * 1024 * 1024
)
# Multipart headers and boundaries are not file content, but they still need a
# hard request-level ceiling before Starlette parses/spools UploadFile objects.
MAX_UPLOAD_REQUEST_BYTES = MAX_UPLOAD_BATCH_BYTES + max(
    1024 * 1024,
    MAX_UPLOAD_FILES * 4096,
)
MAX_PREVIEW_SCAN_BYTES = _positive_int_env(
    "MAX_PREVIEW_SCAN_BYTES", 64 * 1024 * 1024, 1024 * 1024 * 1024
)
MAX_PREVIEW_DECOMPRESSED_BYTES = _positive_int_env(
    "MAX_PREVIEW_DECOMPRESSED_BYTES", 128 * 1024 * 1024, 2 * 1024 * 1024 * 1024
)
MAX_PREVIEW_LINE_BYTES = _positive_int_env(
    "MAX_PREVIEW_LINE_BYTES", 2 * 1024 * 1024, 64 * 1024 * 1024
)
MAX_PREVIEW_XLSX_ENTRIES = _positive_int_env(
    "MAX_PREVIEW_XLSX_ENTRIES", 10_000, 100_000
)
