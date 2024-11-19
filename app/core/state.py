from typing import Set

# 存储所有正在运行的任务（包括手动触发和定时触发）
running_tasks: Set[str] = set()