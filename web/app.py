import secrets
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import sys
from pathlib import Path
import json

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.store import load_record
from core.match import generate_shortlist
from core.config import RECORDS_DIR, REQUIREMENTS_DIR, TALENT_POOL_ADMIN_TOKEN
from core.review import get_review_queue

app = FastAPI(title="Bloodhound Talent Pool Manager")
templates = Jinja2Templates(directory=str(project_root / "web" / "templates"))

AUTH_COOKIE = "talent_pool_admin_token"

def _authorized(request: Request) -> bool:
    if not TALENT_POOL_ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin token is not configured")
    provided = (
        request.headers.get("x-admin-token")
        or request.cookies.get(AUTH_COOKIE)
        or request.query_params.get("token")
    )
    return bool(provided) and secrets.compare_digest(provided, TALENT_POOL_ADMIN_TOKEN)

def _require_auth(request: Request):
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="Authentication required")

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request, token: str | None = None):
    if token and TALENT_POOL_ADMIN_TOKEN and secrets.compare_digest(token, TALENT_POOL_ADMIN_TOKEN):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(AUTH_COOKIE, token, httponly=True, samesite="strict")
        return response
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    _require_auth(request)
    # Load basic stats
    candidate_count = len(list(RECORDS_DIR.glob("*.json")))
    jobs = []
    if REQUIREMENTS_DIR.exists():
        for req_file in REQUIREMENTS_DIR.glob("*.json"):
            with open(req_file, "r", encoding="utf-8") as f:
                jobs.append(json.load(f))
                
    return templates.TemplateResponse(request=request, name="index.html", context={
        "candidate_count": candidate_count,
        "jobs": jobs
    })

@app.get("/candidates", response_class=HTMLResponse)
async def candidates_list(request: Request):
    _require_auth(request)
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
    return templates.TemplateResponse(request=request, name="candidates.html", context={"candidates": candidates})

@app.get("/match/{job_id}", response_class=HTMLResponse)
async def match_job(request: Request, job_id: str):
    _require_auth(request)
    try:
        report = generate_shortlist(job_id, top_n=5)
    except Exception as e:
        report = {"error": str(e), "shortlist": []}
        
    return templates.TemplateResponse(request=request, name="match.html", context={"job_id": job_id, "report": report})

@app.get("/review", response_class=HTMLResponse)
async def review_queue(request: Request):
    _require_auth(request)
    return templates.TemplateResponse(request=request, name="review.html", context={"cases": get_review_queue()})

def start_server():
    import uvicorn
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    start_server()
