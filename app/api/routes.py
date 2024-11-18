from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from app.core import settings, logger
from app.modules import Alist2Strm
from pydantic import BaseModel
import traceback
from contextlib import suppress
import asyncio
import os
from typing import List, Optional

api_key_header = APIKeyHeader(name="Authorization")

async def verify_request(api_token: str = Depends(api_key_header)):
    """验证 API token"""
    if api_token != settings.API_TOKEN:
        logger.error(f"API 请求失败 token 为 {api_token}")
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )
    return api_token

router = APIRouter(
    prefix="/api", 
    dependencies=[Depends(verify_request)]
)

# 添加测试路由
@router.get("/")
async def test():
    """
    Status API
    """
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "message": "API 服务正常运行"
    }

class TaskRequest(BaseModel):
    task_id: str

@router.post("/strm/run")
async def trigger_alist2strm(request: TaskRequest = None):
    """
    手动执行 Alist2Strm 任务
    
    :param request: 任务请求参数，可选。若不提供则运行所有任务
    """
    if not settings.AlistServerList:
        raise HTTPException(status_code=404, detail="未检测到任何 Alist2Strm 模块配置")

    try:
        # 运行单个任务
        if request and request.task_id:
            task_id = request.task_id         
            server = next((s for s in settings.AlistServerList if s["id"] == task_id), None)
            if not server:
                raise HTTPException(status_code=404, detail=f"未找到 ID 为 {task_id} 的任务")
            
            logger.info(f"API 触发 Alist2Strm 任务: {task_id}")
            asyncio.create_task(Alist2Strm(**server).run())
            return {"status": "success", "message": f"任务 {task_id} 已提交"}
        
        # 运行所有任务
        for server in settings.AlistServerList:
            logger.info(f"API 触发 Alist2Strm 任务: {server['id']}")
            asyncio.create_task(Alist2Strm(**server).run())
        return {"status": "success", "message": "所有任务已提交"}
            
    except Exception as e:
        error_msg = f"任务执行失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=f"任务执行失败: {str(e)}")

class LogResponse(BaseModel):
    files: List[str]
    total: int

@router.get("/logs", response_model=Optional[LogResponse])
async def get_logs(filename: Optional[str] = None):
    """
    获取日志文件
    
    :param filename: 指定日志文件名 (格式: YYYY-MM-DD), 不指定则返回日志文件列表
    :return: 文件列表或文件下载响应
    """
    logs_dir = "logs"
    
    # 确保日志目录存在
    if not os.path.exists(logs_dir):
        raise HTTPException(status_code=404, detail="日志目录不存在")
    
    # 如果指定了日志文件名
    if filename:
        log_file = os.path.join(logs_dir, f"{filename}.log")
        if not os.path.exists(log_file):
            raise HTTPException(status_code=404, detail=f"未找到 {filename} 的日志文件")
        return FileResponse(log_file, filename=f"{filename}.log")
    
    # 获取所有日志文件列表
    log_files = []
    for file in os.listdir(logs_dir):
        if file.endswith('.log'):
            log_files.append(file.replace('.log', ''))
    
    log_files.sort(reverse=True)  # 按日期降序排序
    
    return LogResponse(
        files=log_files,
        total=len(log_files)
    )