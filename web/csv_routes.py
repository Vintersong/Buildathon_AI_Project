"""
CSV bulk ingest routes, separated from app.py to keep it readable.
Mount with: app.include_router(csv_router)
"""
import uuid
import threading

from fastapi import APIRouter, HTTPException, UploadFile, File

from .csv_tasks import create_task, get_task, prune_old_tasks
from core.csv_ingest import stream_ingest_file

csv_router = APIRouter(prefix="/api/intake/csv", tags=["csv-ingest"])

# Max upload size: 50 MB (raw bytes check before parsing)
_MAX_BYTES = 50 * 1024 * 1024


_SUPPORTED_SUFFIXES = (".csv", ".xlsx", ".xlsm")


@csv_router.post("", summary="Start a background spreadsheet bulk ingest")
async def start_csv_ingest(file: UploadFile = File(...)):
    """
    Upload a CSV/Excel file and start a background ingest task.
    Returns {task_id} immediately — poll GET /api/intake/csv/{task_id} for progress.
    """
    filename = file.filename or ""
    if not filename.lower().endswith(_SUPPORTED_SUFFIXES):
        raise HTTPException(status_code=400, detail="Only .csv, .xlsx, and .xlsm files are accepted")

    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) // 1024 // 1024} MB). Max 50 MB.",
        )

    task_id = uuid.uuid4().hex
    progress = create_task(task_id)
    prune_old_tasks(keep=20)

    # Run in a background thread so the HTTP response returns immediately
    thread = threading.Thread(
        target=stream_ingest_file,
        args=(content, filename, progress),
        daemon=True,
        name=f"csv-ingest-{task_id[:8]}",
    )
    thread.start()

    return {"task_id": task_id, "status": "started"}


@csv_router.get("/{task_id}", summary="Poll CSV ingest progress")
async def get_csv_ingest_status(task_id: str):
    """
    Returns current progress for a CSV ingest task.
    `done: true` means the task has finished (check `failed` for errors).
    """
    prog = get_task(task_id)
    if not prog:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return prog.to_dict()
