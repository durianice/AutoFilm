import asyncio
import json
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from app.api.routes import execute_single_task
from app.core import settings, logger
from app.modules.alist.v3.client import AlistClient
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


async def refresh_fs_list(task_id: str, sub_dir: str = "") -> bool:
    """
    刷新文件列表缓存
    """
    server = next((s for s in settings.AlistServerList if s["id"] == task_id), None)
    if not server:
        raise HTTPException(status_code=404, detail=f"未找到 ID 为 {task_id} 的任务")
    url = server.get("url", "")
    username = server.get("username", "")
    password = server.get("password", "")
    token = server.get("token", "")
    client = AlistClient(
        url, username, password, token
    )

    """递归刷新文件列表缓存"""
    async def refresh_fs_list_task(path: str):
        for path in await client.async_api_fs_list(path, refresh=True):
            if path.is_dir:
                await refresh_fs_list_task(path.path)

    full_sub_path = server["source_dir"] + "/" + sub_dir
    full_sub_path = full_sub_path.replace("//", "/")
    try:
        # 尝试直接刷新子目录缓存
        await refresh_fs_list_task(full_sub_path)
        return True
    except Exception as _:
        # 如果直接刷新失败，则先刷新父目录缓存，再刷新子目录缓存
        try:
            await client.async_api_fs_list(server["source_dir"], refresh=True)
            await refresh_fs_list_task(full_sub_path)
            return True
        except Exception as e:
            logger.error(f"[Webhook] 刷新子目录 {full_sub_path} 的缓存失败：{e}")
            return False

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
    wait: int = Query(default=180, ge=0, description="等待的秒数"),  # 新增 wait 参数，默认值为 180
    _: str = Depends(verify_path_token)
):
    try:
        if not request or not request.data or not request.type_:
            msg = "[Webhook] 无效的请求参数"
            logger.error(msg)
            return {"status": "failed", "message": msg}
    
        # 使用传入的查询参数 type_ 进行判断
        if request.type_ != type_:
            msg = f"[Webhook] 当前请求参数类型 {request.type_} 与指定类型 {type_} 不匹配"
            # logger.warning(msg)
            return {"status": "failed", "message": msg}
        
        logger.debug(f"[Webhook] 类型：<{request.type_}> 请求数据：{request}")

        mediainfo = request.data.get("mediainfo", {})
        fileitem = request.data.get("fileitem", {})

        if not mediainfo or not fileitem:
            msg = "[Webhook] 请求参数 mediainfo 或 fileitem 无效"
            logger.error(msg)
            return {"status": "failed", "message": msg}
        
        category = mediainfo.get("category", {})
        if not category:
            msg = "[Webhook] 请求参数 category 无效"
            logger.error(msg)
            return {"status": "failed", "message": msg}
        
        name = fileitem.get("name", "")

        file_type = fileitem.get("type", "")
        if file_type != "dir":
            msg = f"[Webhook] 当前文件 {name} 类型为 {file_type}"
            logger.error(msg)
            return {"status": "failed", "message": msg}
        
        if wait < 180:
            wait = 180
            logger.warning(f"[Webhook] 由于元文件同步延迟，等待时间最少 180 秒，已自动设置为 180 秒")
        
        task_name = f"{category} - {name}"
        msg = f"[Webhook] 任务 {task_name} 将在 {wait} 秒后开始执行"
        logger.info(msg)
        await send_message(msg)

        # 定义一个异步任务，等待指定秒数后执行任务
        async def delayed_task():
            await asyncio.sleep(wait)
            refresh_result = await refresh_fs_list(task_id=category, sub_dir=name)
            if refresh_result:
                msg = f"[Webhook] 任务 {task_name} 开始执行"
                logger.info(msg)
                await send_message(msg)
                await execute_single_task(task_id=category, sub_dir=name, done_msg=f"{task_name} 已添加到 Emby 媒体库")
            else:
                msg = f"[Webhook] 任务 {task_name} 刷新缓存失败"
                logger.error(msg)
                await send_message(msg)

        asyncio.create_task(delayed_task())
        return {"status": "success", "message": msg}
    except Exception as e:
        msg = f"[Webhook] 任务提交失败：{e}"
        logger.error(msg)
        return {"status": "failed", "message": msg}

