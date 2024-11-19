from asyncio import get_event_loop
import uvicorn
import threading
from sys import path
from os.path import dirname
import platform
from uuid import uuid4

path.append(dirname(dirname(__file__)))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core import settings, logger, scheduler
from app.extensions import LOGO
from app.modules import Alist2Strm, Ani2Alist
from app.core.state import running_tasks


def print_logo() -> None:
    """
    打印 Logo
    """

    print(LOGO)
    print(f" {settings.APP_NAME} {settings.APP_VERSION} ".center(65, "="))
    print("")


def run_fastapi():
    """
    在单独的线程中运行 FastAPI 服务
    """
    # 在 Windows 上禁用热重载，在其他系统上根据 DEBUG 设置决定
    # enable_reload = settings.DEBUG and platform.system() != "Windows"
    
    uvicorn.run(
        "app.api.server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False
    )

if __name__ == "__main__":
    print_logo()

    logger.info(f"AutoFilm {settings.APP_VERSION} 启动中...")
    logger.debug(f"是否开启 DEBUG 模式: {settings.DEBUG}")

    # 启动 FastAPI 服务
    if settings.ENABLE_API:
        api_thread = threading.Thread(target=run_fastapi, daemon=True)
        api_thread.start()
        logger.info(f"API 服务已启动于 http://{settings.API_HOST}:{settings.API_PORT}")

    if settings.AlistServerList:
        logger.info("检测到 Alist2Strm 模块配置，正在添加至后台任务")
        for server in settings.AlistServerList:
            cron = server.get("cron")
            if cron:
                async def job_wrapper(**kwargs):
                    task_id = kwargs['server_config']['id']
                    if task_id in running_tasks:
                        logger.warning(f"任务 {task_id} 正在运行中，跳过本次定时执行")
                        return
                        
                    try:
                        running_tasks.add(task_id)
                        logger.info(f">>> 任务 {task_id} 开始执行 <<<")
                        await Alist2Strm(**kwargs['server_config']).run()
                    finally:
                        running_tasks.discard(task_id)
                        logger.info(f">>> 任务 {task_id} 执行完毕 <<<")

                scheduler.add_job(
                    func=job_wrapper,
                    trigger=CronTrigger.from_crontab(cron),
                    id=f"alist2strm_{server['id']}_{str(uuid4())[:8]}",
                    kwargs={'server_config': server},
                    misfire_grace_time=None,
                )
                logger.info(f'{server["id"]} {cron} 已被添加至后台任务')
            else:
                logger.warning(f'{server["id"]} 未设置 cron')
    else:
        logger.warning("未检测到 Alist2Strm 模块配置")

    if settings.Ani2AlistList:
        logger.info("检测到 Ani2Alist 模块配置，正在添加至后台任务")
        for server in settings.Ani2AlistList:
            cron = server.get("cron")
            if cron:
                scheduler.add_job(
                    Ani2Alist(**server).run, trigger=CronTrigger.from_crontab(cron)
                )
                logger.info(f'{server["id"]} 已被添加至后台任务')
            else:
                logger.warning(f'{server["id"]} 未设置 cron')
    else:
        logger.warning("未检测到 Ani2Alist 模块配置")

    scheduler.start()
    logger.info("AutoFilm 启动完成")

    try:
        get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("AutoFilm 程序退出！")
