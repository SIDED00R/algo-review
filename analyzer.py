import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

GPT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
_MAX_TOKENS_REVIEW = int(os.environ.get("OPENAI_MAX_TOKENS", "2048"))
_MAX_TOKENS_REPORT = int(os.environ.get("OPENAI_REPORT_MAX_TOKENS", "1024"))


def analyze_code(problem_info: dict, problem_statement: str, code: str) -> dict:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

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
    )

    raw = response.choices[0].message.content.strip()
    result = json.loads(raw)

    if result.get("efficiency") not in ("good", "ok", "poor"):
        result["efficiency"] = "ok"

    return result


def get_cumulative_analysis(tag_stats: list[dict], review_history: list[dict]) -> str:
    if not tag_stats:
        return "아직 분석 데이터가 없습니다. 더 많은 문제를 풀어보세요."

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

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
    )

    return response.choices[0].message.content.strip()
