"""Learning Engine routes — extracted from main.py."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/learning", tags=["Learning"])


class LearnFixRequest(BaseModel):
    error_type: str
    error_text: str
    fix: str
    file_pattern: str = ""
    job_id: str = ""


@router.post("/learn-fix")
async def learning_learn_fix(req: LearnFixRequest):
    from services.learning_engine import get_learning_engine

    engine = get_learning_engine()
    engine.learn_fix(req.error_type, req.error_text, req.fix, req.file_pattern, req.job_id)
    return {"learned": True}


@router.get("/fixes")
async def learning_fixes(error_type: str | None = None, limit: int = 10):
    from services.learning_engine import get_learning_engine

    engine = get_learning_engine()
    return {"fixes": engine.retrieve_fixes(error_type=error_type, limit=limit)}


@router.get("/recommendations")
async def learning_recommend(tech_stack: str | None = None):
    tags = tech_stack.split(",") if tech_stack else None
    from services.learning_engine import get_learning_engine

    engine = get_learning_engine()
    return {
        "architectures": engine.recommend_architecture(tags),
        "deployments": engine.recommend_deployment(tags[0] if tags else None),
        "prompts": engine.recommend_prompts(),
    }


@router.get("/context/{job_id}")
async def learning_context(job_id: str):
    from services.learning_engine import get_learning_engine

    engine = get_learning_engine()
    return engine.get_context_for_job(job_id)


@router.get("/statistics")
async def learning_statistics():
    from services.learning_engine import get_learning_engine

    engine = get_learning_engine()
    return engine.get_statistics()


# ── v12.5 Learning Feedback Loop ─────────────────────────────────────────


@router.post("/ingest")
def ingest_learning_data(data: dict = ...):
    from services.learning_feedback_service import get_learning_feedback_service

    service = get_learning_feedback_service()
    feedback_type = data.get("feedback_type", "evaluation")
    if feedback_type == "evaluation":
        result = service.ingest_evaluation_result(data.get("run", data))
    elif feedback_type == "benchmark":
        result = service.ingest_benchmark_score(data)
    elif feedback_type == "regression":
        result = service.ingest_regression_report(data)
    elif feedback_type == "deployment":
        result = service.ingest_deployment_outcome(data)
    elif feedback_type == "healing":
        result = service.ingest_healing_statistics(data)
    else:
        result = service.ingest_evaluation_result(data)
    return {"success": True, "result": result}


@router.get("/patterns")
def get_learning_patterns(
    pattern_type: str | None = None,
    category: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 100,
):
    from database.memory_store import mem_list_learning_patterns

    patterns = mem_list_learning_patterns(
        pattern_type=pattern_type,
        category=category,
        min_confidence=min_confidence,
        limit=limit,
    )
    return {"patterns": patterns}


@router.get("/feedback-recommendations")
def get_learning_recommendations(
    recommendation_type: str | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = 100,
):
    from database.memory_store import mem_list_learning_recommendations

    recs = mem_list_learning_recommendations(
        recommendation_type=recommendation_type,
        category=category,
        status=status,
        limit=limit,
    )
    return {"recommendations": recs}


@router.get("/insights")
def get_learning_insights_api(
    category: str | None = None,
    limit: int = 20,
):
    from database.memory_store import mem_get_learning_insights

    insights = mem_get_learning_insights(category=category, limit=limit)
    return {"insights": insights}