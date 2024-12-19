import asyncio
import json
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from app.api.routes import execute_single_task
from app.core import settings, logger
from app.utils.bot import send_message

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
async def run_single_task(
    request: WebhookRequest, 
    type_: str = Query(default="nothing_to_do"),  # 从查询参数中获取 type，默认不执行
    wait: int = Query(default=0, ge=0, description="等待的秒数"),  # 新增 wait 参数，默认值为 0
    _: str = Depends(verify_path_token)
):
    if not request or not request.data or not request.type_:
        msg = "[Webhook] 未指定请求数据，跳过执行"
        logger.error(msg)
        return {"status": "failed", "message": msg}
    
    # 使用传入的查询参数 type_ 进行判断
    if request.type_ != type_:
        msg = f"[Webhook] 当前类型：{request.type_}，与指定类型 {type_} 不匹配，跳过执行"
        logger.error(msg)
        return {"status": "failed", "message": msg}

    request_data = request.data
    mediainfo = request_data.get("mediainfo", {})
    if not mediainfo:
        msg = "[Webhook] 当前请求数据中未包含 mediainfo 字段，跳过执行"
        logger.error(msg)
        return {"status": "failed", "message": msg}
    fileitem = request_data.get("fileitem", {})
    if not fileitem:
        msg = "[Webhook] 当前请求数据中未包含 fileitem 字段，跳过执行"
        logger.error(msg)
        return {"status": "failed", "message": msg}
    
    category = mediainfo.get("category", {})
    full_path = fileitem.get("path", "")
    task_id = category
    if not task_id:
        msg = "[Webhook] 当前请求数据中未包含 category 字段，跳过执行"
        logger.error(msg)
        return {"status": "failed", "message": msg}
    
    msg = f"[Webhook] 提交任务成功，任务将在 {wait} 秒后开始执行\n类别：{task_id}\n源文件路径：{full_path}"
    logger.info(msg)
    await send_message(msg)

    # 定义一个异步任务，等待指定秒数后执行任务
    async def delayed_task():
        await asyncio.sleep(wait)  # 等待指定的秒数
        msg = f"[Webhook] 任务开始执行\n类别：{task_id}\n源文件路径：{full_path}"
        logger.info(msg)
        await send_message(msg)
        await execute_single_task(task_id)  # 执行任务

    # 使用 asyncio.create_task 创建异步任务
    asyncio.create_task(delayed_task())

    # 立即返回任务提交成功的信息
    return {"status": "success", "message": msg}
