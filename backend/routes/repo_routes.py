"""Repository analyzer routes — extracted from main.py."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/repo", tags=["Repository Analyzer"])


class RepoAnalyzeRequest(BaseModel):
    repo_path: str
    model: str | None = "cloud"


class RepoImproveRequest(BaseModel):
    repo_path: str
    model: str | None = "cloud"
    auto_fix: bool = True
    generate_tests: bool = True


class RepoCreatePRRequest(BaseModel):
    repo_path: str
    github_token: str
    repo_full_name: str
    branch_name: str = "auto-improve"
    base_branch: str = "main"
    title: str = "Automated code quality improvements"
    body: str = "AI-driven improvements including fixes, tests, and documentation."
    model: str | None = "cloud"


@router.post("/analyze")
async def repo_analyze(req: RepoAnalyzeRequest):
    from services.repo_analyzer_service import analyze_repository

    try:
        result = analyze_repository(req.repo_path, model=req.model or "cloud")
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300])


@router.post("/improve")
async def repo_improve(req: RepoImproveRequest):
    from services.repo_analyzer_service import improve_repository

    try:
        result = improve_repository(
            req.repo_path,
            model=req.model or "cloud",
            auto_fix=req.auto_fix,
            generate_tests=req.generate_tests,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300])


@router.post("/create-pr")
async def repo_create_pr(req: RepoCreatePRRequest):
    from services.repo_analyzer_service import create_pr

    try:
        result = create_pr(
            req.repo_path,
            req.github_token,
            req.repo_full_name,
            branch_name=req.branch_name,
            base_branch=req.base_branch,
            title=req.title,
            body=req.body,
            model=req.model or "cloud",
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:300])
