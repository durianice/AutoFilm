from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

def get_scheduler_jobs():
    """
    获取调度器中的所有任务信息
    Returns:
        list: 包含所有任务信息的列表
    """
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time,
            'trigger': str(job.trigger),
            'running': job.pending,
            'args': job.args,
            'kwargs': job.kwargs
        })
    return jobs