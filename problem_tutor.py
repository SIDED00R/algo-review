"""문제 질문 답변 — 뷰어가 보낸 문제 본문·질문(앞선 대화 포함)으로 답을 만든다.

소유자 요청이면 claude_gate 의 Claude 답을 쓰고, 없으면 OpenAI 호환 엔드포인트(llm_client)로 묻는다.
답과 함께 답한 모델의 표시 이름을 돌려준다(뷰어가 답 옆에 적는다).
"""
from claude_gate import claude_answer
from config import settings
from constants import PLATFORM_LABELS
from llm_client import choice_text, get_client, require_choice

_MAX_TOKENS = settings.openai_max_tokens or 2048

_SYSTEM_PROMPT = """당신은 경쟁 프로그래밍 튜터입니다. 사용자가 아래 문제를 풀다가 질문합니다.
질문 범위에 맞춰 답하세요 — 힌트를 물으면 힌트만, 풀이나 코드를 물으면 풀이나 코드를 줍니다.
사용자 코드가 함께 오면 질문과 관련해서만 코드를 봅니다.
모든 답은 한국어 마크다운으로 쓰고, 수식은 $...$ 로 감쌉니다."""


def build_user_prompt(platform: str, problem_ref: str, title: str, statement: str,
                      question: str, code: str = "", history: list[dict] | None = None) -> str:
    """history 는 앞선 [{"question", "answer"}] 이다. 서버는 대화를 저장하지 않는다."""
    parts = [
        "## 문제",
        f"- 플랫폼: {PLATFORM_LABELS[platform]}",
        f"- 문제 식별자: {problem_ref}",
        f"- 제목: {title or '미상'}",
        "",
        statement.strip() or "(본문 없음 — 제목과 식별자로만 판단하세요)",
    ]
    if code.strip():
        parts += ["", "## 사용자 코드", "```", code, "```"]
    for turn in history or []:
        parts += ["", "## 앞선 질문", turn["question"], "", "## 앞선 답변", turn["answer"]]
    parts += ["", "## 이번 질문", question]
    return "\n".join(parts)


def answer_question(platform: str, problem_ref: str, title: str, statement: str,
                    question: str, code: str = "", history: list[dict] | None = None) -> tuple[str, str]:
    """(답, 답한 모델 표시 이름). 빈 답은 사람이 읽을 수 있는 ValueError 로 알린다."""
    user_prompt = build_user_prompt(platform, problem_ref, title, statement, question, code, history)

    claude_text = claude_answer(_SYSTEM_PROMPT, user_prompt)
    if claude_text is not None:
        return claude_text, "Claude"

    model = settings.openai_model or "gpt-4o"
    response = get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=_MAX_TOKENS,
    )
    require_choice(response)
    text = choice_text(response)
    if not text:
        raise ValueError("AI 가 빈 응답을 돌려줬습니다. 잠시 후 다시 시도해주세요.")
    if response.choices[0].finish_reason == "length":
        text += "\n\n_(⚠️ 답이 길어 뒷부분이 잘렸습니다.)_"
    return text, model
