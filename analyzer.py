import json
import threading

from openai import OpenAI

from config import settings

GPT_MODEL = settings.openai_model or "gpt-4o"
_MAX_TOKENS_REVIEW = settings.openai_max_tokens or 2048
_MAX_TOKENS_REPORT = settings.openai_report_max_tokens
# openai SDK 기본값은 read 600s·재시도 2회 — 제공자가 멎으면 워커 스레드가 수십 분 잡힌다.
# timeout 만 줄이면 실효 상한이 3×timeout + 백오프가 되므로 재시도 횟수도 함께 못박는다.
_API_TIMEOUT = settings.openai_timeout
_MAX_RETRIES = 1

# 클라이언트는 모듈 레벨에 하나만 둔다 — 호출마다 새로 만들면 httpx 커넥션 풀과 TLS
# 핸드셰이크를 매번 버린다(문제 뷰어는 한 요청에 섹션 4개를 동시 번역한다).
# settings 는 프로세스 기동 시 고정되므로 재생성할 이유가 없다.
_client = None
_client_lock = threading.Lock()


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = OpenAI(api_key=settings.openai_api_key,
                             base_url=settings.openai_base_url or None,
                             timeout=_API_TIMEOUT, max_retries=_MAX_RETRIES)
    return _client


_STRING_FIELDS = ("complexity", "better_algorithm", "feedback")


def normalize_review_result(result: dict) -> dict:
    """LLM 응답을 저장 가능한 형태로 정규화한다(생산자 한 곳에서 끝낸다).

    `.get(key, default)` 는 **키가 있고 값이 None** 이면 default 를 적용하지 않는다.
    LLM 이 `"complexity": null` 을 주면 그 None 이 NOT NULL 컬럼으로 흘러가 저장이
    IntegrityError 로 죽고, 이미 과금된 응답과 tag_stats 첫 집계가 롤백으로 함께 사라진다.
    저장 경로가 둘이라(save_review / update_pending_review) 소비처마다 막으면 한쪽이
    빠진다 — 실제로 update_pending_review 만 빠져 있었다.
    """
    if result.get("efficiency") not in ("good", "ok", "poor"):
        result["efficiency"] = "ok"
    for key in _STRING_FIELDS:
        result[key] = result.get(key) or ""
    return result


def _require_choice(response) -> None:
    """choices 가 비면 아래 인덱싱이 IndexError 로 새어 "코드 분석 실패: list index out of
    range" 라는 해독 불가 500 이 된다. .env.example 이 Gemini 호환 엔드포인트를 1급 대안으로
    안내하므로(응답 형태가 미묘하게 다를 수 있다) 현실적인 경계다."""
    if not getattr(response, "choices", None):
        raise ValueError("AI 응답에 결과가 없습니다. 제공자 설정(OPENAI_BASE_URL·모델)을 확인해주세요.")


def analyze_code(problem_info: dict, problem_statement: str, code: str) -> dict:
    client = _get_client()

    tags_str = ", ".join(problem_info["tags"]) if problem_info["tags"] else "태그 없음"
    platform = (problem_info.get("platform") or "boj").lower()
    platform_label = "Codeforces" if platform == "codeforces" else "백준"
    problem_label = problem_info.get("problem_ref") or problem_info.get("id")

    system_prompt = """당신은 알고리즘 코드 리뷰 전문가입니다.
주어진 경쟁 프로그래밍 문제와 사용자의 풀이 코드를 분석하여 구체적이고 교육적인 피드백을 제공합니다.
모든 응답은 반드시 한국어로 작성하세요. JSON 형식으로만 응답하세요."""

    user_prompt = f"""다음 {platform_label} 문제와 풀이 코드를 분석해주세요.

## 문제 정보
- 플랫폼: {platform_label}
- 문제 식별자: {problem_label}
- 제목: {problem_info['title']}
- 난이도: {problem_info['tier_name']} (티어 {problem_info['tier']})
- 알고리즘 태그: {tags_str}

## 문제 설명
{problem_statement[:2000]}

## 제출 코드
```
{code}
```

## 분석 지시사항
1. 시간복잡도/공간복잡도 분석
2. 이 문제 난이도와 태그에 비해 풀이가 효율적인지 판단
3. 더 적합한 알고리즘이 있다면 구체적으로 제안 (예: "O(N²) DP인데 O(N log N) 정렬+이분탐색으로 풀 수 있음")
4. 코드 품질 전반 평가 (가독성, 변수명, 엣지케이스 처리 등)

다음 JSON 형식으로 응답하세요. 모든 텍스트는 반드시 한국어로 작성하세요:
{{
  "efficiency": "good 또는 ok 또는 poor",
  "complexity": "분석된 시간복잡도 (예: O(N log N))",
  "better_algorithm": "더 적합한 알고리즘 설명 (한국어) 또는 null",
  "feedback": "전체 피드백 (한국어, 마크다운 사용 가능, 300자 이상)",
  "strengths": ["잘한 점1 (한국어)", "잘한 점2 (한국어)"],
  "weaknesses": ["부족한 점1 (한국어)", "부족한 점2 (한국어)"]
}}

efficiency 기준:
- good: 최적이거나 거의 최적에 가까운 풀이
- ok: 통과는 하지만 더 나은 방법이 있는 풀이
- poor: 비효율적이거나 알고리즘 선택이 부적합한 풀이"""

    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=_MAX_TOKENS_REVIEW,
        timeout=_API_TIMEOUT,
    )

    _require_choice(response)
    if response.choices[0].finish_reason == "length":
        # max_tokens 에 걸려 JSON 이 중간에 잘렸다 — json.loads 로 넘기면 유료 호출을 다 쓴
        # 뒤 알아보기 힘든 JSONDecodeError 로 500이 난다. 사람이 읽을 수 있는 에러로 분기한다.
        raise ValueError(
            f"AI 응답이 최대 토큰({_MAX_TOKENS_REVIEW})을 초과해 잘렸습니다. "
            "코드가 너무 길 수 있습니다."
        )

    raw = (response.choices[0].message.content or "").strip()
    if not raw:
        raise ValueError("AI 가 빈 응답을 돌려줬습니다. 잠시 후 다시 시도해주세요.")
    result = json.loads(raw)

    return normalize_review_result(result)


def get_cumulative_analysis(tag_stats: list[dict], review_history: list[dict]) -> str:
    # 빈 입력 안내는 라우터가 400 으로 낸다(routes/report.py) — 여기 두면 같은 문구가
    # 두 곳에 정의돼 어느 쪽이 정본인지 알 수 없다.

    client = _get_client()

    stats_text = "\n".join(
        f"- {s['tag']}: 총 {s['total_count']}회 (잘함 {s['good_count']}회, 부족 {s['poor_count']}회)"
        for s in tag_stats[:20]
    )

    recent_problems = "\n".join(
        f"- [{r['tier']}티어] {r['title']} ({', '.join(r['tags'][:3])}) → {r['efficiency']}"
        for r in review_history[:10]
    )

    prompt = f"""다음은 알고리즘 문제 풀이 누적 데이터입니다. 모든 분석은 반드시 한국어로 작성하세요.

## 태그별 통계
{stats_text}

## 최근 풀이 기록
{recent_problems}

이 데이터를 분석하여:
1. 강점 알고리즘 영역 (2-3가지)
2. 취약 알고리즘 영역 (2-3가지)
3. 학습 우선순위 추천
4. 전반적인 성장 방향

을 300자 이상으로 설명해주세요."""

    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=_MAX_TOKENS_REPORT,
        timeout=_API_TIMEOUT,
    )

    # 인덱싱보다 먼저 확인한다 — 순서가 뒤집히면 choices 가 빈 응답에서 IndexError 가 나고
    # 가드가 도달하지 못한다(analyze_code 는 올바른 순서였는데 여기만 뒤집혀 있었다).
    _require_choice(response)
    if response.choices[0].finish_reason == "length":
        # max_tokens 에 걸려 리포트가 중간에서 잘렸다 — 캐시가 없어 매번 재생성되므로
        # 잘린 채로 200을 내보내지 않고 사람이 읽을 수 있는 에러로 분기한다.
        raise ValueError(
            f"AI 응답이 최대 토큰({_MAX_TOKENS_REPORT})을 초과해 잘렸습니다. "
            "데이터가 너무 많을 수 있습니다."
        )

    return (response.choices[0].message.content or "").strip()
