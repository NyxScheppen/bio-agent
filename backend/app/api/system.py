from fastapi import APIRouter
from app.services.system_service import get_system_info

router = APIRouter()

@router.get("/api/system-info")
async def system_info():
    """
    获取当前后端运行环境配置
    """
    return {
        "status": "success",
        "data": get_system_info()
    }