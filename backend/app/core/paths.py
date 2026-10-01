from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]   # /mnt/d/desktop/iGEM_BioAI_Agent/backend

STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
GENERATED_DIR = STORAGE_DIR / "generated"
TEMP_DIR = STORAGE_DIR / "temp"
DB_DIR = BASE_DIR / "db_data"

for path in [STORAGE_DIR, UPLOAD_DIR, GENERATED_DIR, TEMP_DIR, DB_DIR]:
    path.mkdir(parents=True, exist_ok=True)