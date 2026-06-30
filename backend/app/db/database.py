import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.paths import DB_DIR

DB_PATH = os.path.join(DB_DIR, "app.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# SQLite 单文件数据库，适合本地开发和小型项目
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """
    FastAPI 依赖注入用的数据库 Session
    用完自动关闭
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()