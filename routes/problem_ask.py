"""문제 뷰어 질문 — 열린 문제에 대한 질문에 LLM 답을 돌려준다(대화는 저장하지 않는다)."""
from fastapi import APIRouter

import problem_tutor
from demo_mode import DEMO_PROBLEM_ANSWERS, IS_DEMO
from routes.helpers import require_openai_key, run_llm
from routes.models import ProblemAskRequest

router = APIRouter()


@router.post("/api/problem/ask")
def ask_about_problem(req: ProblemAskRequest):
    if IS_DEMO:
        return {"answer": DEMO_PROBLEM_ANSWERS[req.platform], "model": "데모"}
    require_openai_key()
    answer, model = run_llm(
        "질문 답변 실패", problem_tutor.answer_question,
        req.platform, req.problem_ref, req.title, req.statement, req.question, req.code,
        [turn.model_dump() for turn in req.history],
    )
    return {"answer": answer, "model": model}
