import json
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from app.api.routes import execute_single_task
from app.core import settings, logger

# 验证路径 token
def verify_path_token(path_token: str = Path(..., description="Path token for authentication")):
    """
    验证路径中的 token
    """
    if path_token == settings.WEBHOOK_TOKEN:
        return True
    raise HTTPException(status_code=401, detail="Not authenticated")

router = APIRouter(
    prefix="/webhooks/{path_token}"
)

# 测试路由
@router.get("/")
async def test(_: str = Depends(verify_path_token)):
    """
    测试 API，验证路径 token
    """
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "message": "Webhooks 服务正常运行"
    }

class WebhookRequest(BaseModel):
    data: Dict
    type_: str = Field(..., alias="type")  # 使用 type_ 作为字段名，type 作为别名

    class Config:
        populate_by_name = True  # 允许通过字段名访问
# 运行单个任务
@router.post("/single")
async def run_single_task(request: WebhookRequest, _: str = Depends(verify_path_token)):
    if not request or not request.data or not request.type_:
        msg = "[Webhook] 未指定请求数据，跳过执行"
        logger.error(msg)
        return {"status": "failed", "message": msg}
    if request.type_ != "metadata.scrape":
        msg = f"[Webhook] 当前类型：{request.type_}，跳过执行"
        logger.error(msg)
        return {"status": "failed", "message": msg}
    request_data = request.data
    mediainfo = request_data.get("mediainfo", {})
    category = mediainfo.get("category", {})
    task_id = category
    if not task_id:
        msg = "[Webhook] 当前请求数据中未包含 category 字段，跳过执行"
        logger.error(msg)
        return {"status": "failed", "message": msg}
    msg = f"[Webhook] 开始处理STRM文件\n类别：{task_id}"
    logger.info(msg)
    return await execute_single_task(task_id)
