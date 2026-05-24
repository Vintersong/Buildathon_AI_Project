"""
In-process task registry for CSV background ingests.
Keyed by task_id (UUID hex). Stored in memory — survives for the process lifetime.
"""
from typing import Optional
from core.csv_ingest import CSVIngestProgress

_tasks: dict[str, CSVIngestProgress] = {}


def create_task(task_id: str) -> CSVIngestProgress:
    prog = CSVIngestProgress()
    _tasks[task_id] = prog
    return prog


def get_task(task_id: str) -> Optional[CSVIngestProgress]:
    return _tasks.get(task_id)


def prune_old_tasks(keep: int = 10) -> None:
    """Keep only the N most recent completed tasks to avoid memory creep."""
    done = [k for k, v in _tasks.items() if v.done]
    for k in done[:-keep]:
        del _tasks[k]
