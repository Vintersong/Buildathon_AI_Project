from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import sys
from pathlib import Path
import json

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.store import load_record
from core.match import generate_shortlist
from core.config import RECORDS_DIR, REQUIREMENTS_DIR, INDEXES_DIR

app = FastAPI(title="Bloodhound Talent Pool Manager")
templates = Jinja2Templates(directory=str(project_root / "web" / "templates"))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Load basic stats
    candidate_count = len(list(RECORDS_DIR.glob("*.json")))
    jobs = []
    if REQUIREMENTS_DIR.exists():
        for req_file in REQUIREMENTS_DIR.glob("*.json"):
            with open(req_file, "r", encoding="utf-8") as f:
                jobs.append(json.load(f))
                
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "candidate_count": candidate_count,
        "jobs": jobs
    })

@app.get("/candidates", response_class=HTMLResponse)
async def candidates_list(request: Request):
    candidates = []
    if RECORDS_DIR.exists():
        for f in RECORDS_DIR.glob("*.json"):
            rec = load_record(f.stem)
            if rec:
                candidates.append({
                    "id": f.stem,
                    "name": rec.identity.primary_name,
                    "headline": rec.profile.headline,
                    "status": rec.state.status,
                    "score": rec.scores.extraction_confidence
                })
    return templates.TemplateResponse("candidates.html", {"request": request, "candidates": candidates})

@app.get("/match/{job_id}", response_class=HTMLResponse)
async def match_job(request: Request, job_id: str):
    try:
        report = generate_shortlist(job_id, top_n=5)
    except Exception as e:
        report = {"error": str(e), "shortlist": []}
        
    return templates.TemplateResponse("match.html", {"request": request, "job_id": job_id, "report": report})

def start_server():
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    start_server()
