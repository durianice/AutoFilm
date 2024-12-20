from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from app.core import settings, logger, get_scheduler_jobs
from app.modules import Alist2Strm
from pydantic import BaseModel
import traceback
from contextlib import suppress
import asyncio
import os
from typing import Dict, List, Optional, Set
from app.core.state import running_tasks
from app.utils.bot import send_message

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

# 全局变量
__max_workers = 1  # 每次只允许一个任务运行
semaphore = asyncio.Semaphore(__max_workers)  # 信号量控制并发
task_queue = asyncio.Queue()  # 任务队列，用于排队任务
running_tasks: Set[str] = set()  # 当前正在运行的任务
task_status: Dict[str, str] = {}  # 任务状态跟踪（运行中、排队中）

# 定义任务请求模型
class TaskRequest(BaseModel):
    task_id: str

async def task_worker():
    """
    任务消费者，负责从队列中取出任务并执行。
    """
    while True:
        task_id, new_server, refresh = await task_queue.get()
        try:
            # 更新任务状态为 "运行中"
            task_status[task_id] = "运行中"
            running_tasks.add(task_id)

            # 打印当前任务状态
            logger.info(f"当前正在运行的任务: {list(running_tasks)}")
            logger.info(f"排队中的任务数: {task_queue.qsize()}")

            # 使用信号量限制并发
            async with semaphore:
                logger.info(f"开始执行任务: {task_id}")
                await Alist2Strm(**new_server).run(refresh=refresh)
                logger.info(f"任务 {task_id} 已完成")
                await send_message(f"任务 {task_id} 已完成")
        except Exception as e:
            error_msg = f"任务 {task_id} 执行失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            await send_message(f"[任务执行失败]\n{task_id}\n{error_msg}")
        finally:
            # 清理任务状态
            running_tasks.discard(task_id)
            task_status.pop(task_id, None)
            task_queue.task_done()
            
asyncio.create_task(task_worker())

async def execute_single_task(task_id: str, refresh: bool = False, sub_dir: str = ""):
    """
    提交任务到队列

    :param task_id: 任务 ID
    :param refresh: 是否刷新
    :param sub_dir: 子目录
    :return: 提交结果
    """
    if not settings.AlistServerList:
        raise HTTPException(status_code=404, detail="未检测到任何 Alist2Strm 模块配置")

    # 检查任务是否已经在运行或排队
    if task_id in running_tasks or task_id in task_status:
        return {"status": "warning", "message": f"任务 {task_id} 已在运行或排队中"}

    # 查找任务配置
    server = next((s for s in settings.AlistServerList if s["id"] == task_id), None)
    if not server:
        raise HTTPException(status_code=404, detail=f"未找到 ID 为 {task_id} 的任务")

    try:
        msg = f"触发 Alist2Strm 任务: {task_id}"
        logger.info(msg)
        await send_message(msg)

        # 将任务添加到队列并更新状态为 "排队中"
        new_server = server.copy()
        new_server["sub_dir"] = sub_dir
        await task_queue.put((task_id, new_server, refresh))
        task_status[task_id] = "排队中"

        # 打印当前任务状态
        logger.info(f"任务 {task_id} 已提交到队列")
        logger.info(f"当前正在运行的任务: {list(running_tasks)}")
        logger.info(f"排队中的任务数: {task_queue.qsize()}")

        return {"status": "success", "message": f"任务 {task_id} 已提交到队列"}
    except Exception as e:
        error_msg = f"任务提交失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        await send_message(f"[任务提交失败]\n{task_id}\n{error_msg}")
        raise HTTPException(status_code=500, detail=f"任务提交失败: {str(e)}")

@router.post("/strm/run")
async def trigger_alist2strm(request: TaskRequest = None):
    """
    手动执行 Alist2Strm 任务

    :param request: 任务请求参数，可选。若不提供则运行所有任务
    """
    if not request or not request.task_id:
        return {"status": "failed", "message": "未指定 task_id"}

    # 调用封装的任务执行逻辑
    return await execute_single_task(request.task_id)

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


# @router.get("/config")
# async def get_config():
#     """
#     获取配置
#     """
#     return {
#         "Alist2StrmList": settings.AlistServerList,
#         "Ani2AlistList": settings.Ani2AlistList
#     }

@router.get("/jobs")
async def get_jobs():
    """
    获取调度器中任务和手动添加的任务
    """
    scheduler_jobs = get_scheduler_jobs()
    return {
        "cron": scheduler_jobs,
        "all": running_tasks
    }
