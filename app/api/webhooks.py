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


async def refresh_fs_list(task_id: str, sub_dir: str = "") -> dict:
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
        logger.debug(f"[Webhook] 刷新子目录 {path} 的缓存")
        for path in await client.async_api_fs_list(path, refresh=True):
            if path.is_dir:
                await refresh_fs_list_task(path.path)

    parent_path_list = await client.async_api_fs_list(server["source_dir"], refresh=True)
    sub_path = server["source_dir"] + sub_dir
    latest_paths = []
    is_exist_sub_path = False
    for path in parent_path_list:
        latest_paths.append(path.path)
        if sub_path == path.path:
            is_exist_sub_path = True
    logger.debug(f"[Webhook] 父目录 {server['source_dir']} 的列表：{latest_paths}")

    if is_exist_sub_path:
        logger.debug(f"[Webhook] 子目录 {sub_path} 存在，递归刷新子目录缓存")
        await refresh_fs_list_task(sub_path)

    logger.debug(f"[Webhook] 刷新文件列表缓存完成")

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
            msg = "[Webhook] 未指定请求数据，跳过执行"
            logger.warning(msg)
            return {"status": "failed", "message": msg}
    
        # 使用传入的查询参数 type_ 进行判断
        if request.type_ != type_:
            msg = f"[Webhook] 当前类型：{request.type_}，与指定类型 {type_} 不匹配，跳过执行"
            logger.warning(msg)
            return {"status": "failed", "message": msg}
        
        logger.debug(f"[Webhook] 请求数据：{request}")

        mediainfo = request.data.get("mediainfo", {})
        if not mediainfo:
            msg = "[Webhook] 当前请求数据中未包含 mediainfo 字段，跳过执行"
            logger.warning(msg)
            return {"status": "failed", "message": msg}
        
        fileitem = request.data.get("fileitem", {})
        if not fileitem:
            msg = "[Webhook] 当前请求数据中未包含 fileitem 字段，跳过执行"
            logger.warning(msg)
            return {"status": "failed", "message": msg}
        
        file_type = fileitem.get("type", "")
        if file_type != "dir":
            msg = "[Webhook] 当前文件类型不是目录，跳过执行"
            logger.warning(msg)
            return {"status": "failed", "message": msg}
        
        media_type = mediainfo.get("type", "")
        if media_type == "电视剧" and "Season" in name:
            msg = "[Webhook] 当前路径是电视剧季集，跳过执行"
            logger.warning(msg)
            return {"status": "failed", "message": msg}
        
        category = mediainfo.get("category", {})
        full_path = fileitem.get("path", "")
        name = fileitem.get("name", "")
        task_id = category
        if not task_id:
            msg = "[Webhook] 当前请求数据中未包含 category 字段，跳过执行"
            logger.error(msg)
            return {"status": "failed", "message": msg}
        
        if wait < 180:
            wait = 180
            logger.warning(f"[Webhook] 由于元文件同步延迟，等待时间最少 180 秒，已自动设置为 180 秒")
        
        info = f"类别：{task_id} 源文件路径：{full_path}"
        msg = f"[Webhook] 提交任务成功，任务将在 {wait} 秒后开始执行 - {info}"
        logger.info(msg)
        await send_message(msg)

        # 定义一个异步任务，等待指定秒数后执行任务
        async def delayed_task():
            await asyncio.sleep(wait)
            await refresh_fs_list(task_id, "/" + name)
            msg = f"[Webhook] 任务开始执行 - {info}"
            logger.info(msg)
            await send_message(msg)
            await execute_single_task(task_id, refresh=False, sub_dir=name, meta_str=f"{category} - {name} 已添加到 Emby 媒体库")

        asyncio.create_task(delayed_task())

        # 立即返回任务提交成功的信息
        return {"status": "success", "message": msg}
    except Exception as e:
        msg = f"[Webhook] 任务提交失败，错误信息：{e}"
        logger.error(msg)
        return {"status": "failed", "message": msg}

