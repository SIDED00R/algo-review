# BOJ / Codeforces 코드 리뷰 & 문제 추천

알고리즘 풀이 코드를 AI로 분석하고, 학습 기록을 바탕으로 약한 태그를 추적하는 웹앱입니다.

**라이브 데모**: https://algo-review-demo-707325519995.asia-northeast3.run.app/

> 데모는 실제 API 없이 샘플 데이터로 동작합니다. 모든 기능을 자유롭게 체험해보세요.

현재 지원 범위:
- `BOJ`: 코드 리뷰, 문제 추천, 통계, 제출 기록 import
- `Codeforces`: 코드 리뷰, 문제 추천, 통계, 제출 기록 import, 인앱 문제 뷰어

## 주요 기능

- **코드 리뷰**
  - BOJ 또는 Codeforces 문제 번호와 코드를 입력하면 AI가 시간복잡도, 효율성, 개선점, 강점/약점을 분석합니다.
- **CF 인앱 문제 뷰어**
  - Codeforces 문제를 앱 내에서 바로 보고 한국어 번역까지 제공합니다.
  - 예제 입출력 직접 실행 (Python / C++) 지원
- **기록 import**
  - `BaekjoonHub GitHub` 저장소 import
  - `BOJ 제출 기록` import
  - `Codeforces handle` 기반 import
- **리뷰 기록 조회**
  - 문제별 제출 이력과 상세 피드백을 다시 확인할 수 있습니다.
- **통계 / 리포트**
  - BOJ / Codeforces 플랫폼 전환 탭 제공
  - 태그 통계, 티어(레이팅) 변화, 누적 분석 리포트
- **문제 추천**
  - 약한 태그와 현재 수준 + 도전 난이도를 혼합해 다음 문제를 추천합니다.
  - BOJ / Codeforces 각각 지원

## 로컬 실행

### 1. 요구사항

- Python 3.11+
- OpenAI API 키

### 2. 설치

```bash
git clone https://github.com/SIDED00R/algo-review.git
cd algo-review

python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. 환경변수 설정

프로젝트 루트에 `.env` 파일을 만듭니다.

```env
OPENAI_API_KEY=your_openai_key

# 선택: GitHub OAuth (리뷰 → GitHub push 기능)
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
APP_URL=http://localhost:8000

# 선택: Codeforces 소스 코드 import
CODEFORCES_API_KEY=your_codeforces_key
CODEFORCES_API_SECRET=your_codeforces_secret

# 선택: CORS 허용 출처 (기본값: http://localhost:8080)
# CORS_ORIGINS=http://localhost:8000,https://yourdomain.com

# 선택: PostgreSQL 사용 시
# DB_TYPE=postgres
# DB_NAME=boj_review
# DB_USER=boj_user
# DB_PASSWORD=your_password
# DB_HOST=localhost
# DB_PORT=5432
# DB_SOCKET=/cloudsql/PROJECT:REGION:INSTANCE
```

### 4. 실행

```bash
python -m uvicorn server:app --reload
```

브라우저에서 `http://localhost:8000` 접속

## Codeforces 관련 주의사항

- CF 문제 본문은 공식 API가 제공하지 않으므로 크롤링으로 가져옵니다.
  - 실패 시 리뷰 화면의 `문제 설명` 입력칸에 직접 붙여 넣어도 됩니다.
- CF 소스코드 import는 본인 계정 API Key / Secret이 필요합니다.

## 배포

### Cloud Run (SQLite)

```bash
gcloud run deploy algo-review \
  --source . \
  --region asia-northeast3
```

### Cloud Run + Cloud SQL (PostgreSQL)

```bash
gcloud run deploy algo-review \
  --source . \
  --region asia-northeast3 \
  --add-cloudsql-instances PROJECT:REGION:INSTANCE
```

필수 환경변수:

```env
OPENAI_API_KEY=...
DB_TYPE=postgres
DB_NAME=boj_review
DB_USER=boj_user
DB_PASSWORD=...
DB_SOCKET=/cloudsql/PROJECT:REGION:INSTANCE

# GitHub OAuth (선택)
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
APP_URL=https://your-cloud-run-url

# CF import (선택)
CODEFORCES_API_KEY=...
CODEFORCES_API_SECRET=...
```

### 데모 서버 배포

실제 API 없이 샘플 데이터로 동작하는 데모 서버를 별도로 배포할 수 있습니다.

```bash
gcloud run deploy algo-review-demo \
  --source . \
  --region asia-northeast3 \
  --set-env-vars "DEMO_MODE=true"
```

`DEMO_MODE=true` 설정 시:
- LLM·GitHub·외부 API 호출 없이 mock 응답 반환
- 시딩된 샘플 데이터로 통계·히스토리 표시
- SQLite 사용 (Cloud SQL 불필요)

## 프로젝트 구조

```
.
├── server.py               # FastAPI 앱 초기화, 미들웨어·라우터 등록
├── main.py                 # CLI 인터페이스 (코드 리뷰, 추천, 통계)
├── analyzer.py             # OpenAI GPT 코드 분석
├── recommender.py          # 취약 태그 기반 문제 추천 알고리즘
├── cf_translator.py        # OpenAI를 이용한 CF 문제 본문 한국어 번역
├── demo_mode.py            # 데모 모드 플래그 및 mock 데이터
├── demo_seed.py            # 데모용 SQLite 샘플 데이터 시딩
├── ARCHITECTURE.md         # 레이어 다이어그램 & 호출관계 문서
│
├── clients/                # 외부 API 클라이언트 (각 파일이 하나의 플랫폼 담당)
│   ├── solved_ac.py        # solved.ac API, BOJ 스크래핑, TIER_NAMES 상수
│   ├── codeforces.py       # Codeforces API, 문제 메타/본문 스크래핑
│   ├── github.py           # GitHub OAuth, 파일 push, BaekjoonHub import
│   └── utils.py            # get_problem_url(), 파일 확장자 매핑
│
├── db/                     # DB 레이어 (각 파일이 하나의 테이블 담당)
│   ├── connection.py       # DB 연결 팩토리 (SQLite / PostgreSQL)
│   ├── schema.py           # 테이블 생성 및 마이그레이션
│   ├── reviews.py          # reviews 테이블 CRUD + 티어/태그 집계
│   ├── solved.py           # solved_history 테이블 CRUD
│   └── github_settings.py  # github_settings 테이블 CRUD
│
├── routes/                 # FastAPI 라우터 (각 파일이 하나의 도메인 담당)
│   ├── auth.py             # GitHub OAuth 인증 흐름
│   ├── review.py           # POST /api/review — AI 코드 리뷰
│   ├── github_push.py      # POST /api/push-review — GitHub push
│   ├── problem.py          # GET /api/problem/cf/{ref} — CF 문제 조회
│   ├── execute.py          # POST /api/execute — Python/C++ 코드 실행
│   ├── recommend.py        # GET /api/recommend — 문제 추천
│   ├── history.py          # GET /api/reviews/* — 리뷰 기록 조회
│   ├── solved.py           # /api/solved-history/* — import 기록 관리
│   ├── stats.py            # GET /api/stats, /api/tier-history — 통계
│   ├── report.py           # GET /api/report — 종합 분석 리포트
│   ├── import_github.py    # POST /api/import-github — BaekjoonHub import
│   ├── import_boj.py       # POST /api/import — BOJ 제출 기록 import
│   ├── import_codeforces.py# POST /api/import-codeforces — CF import
│   ├── models.py           # Pydantic 요청/응답 스키마
│   ├── helpers.py          # GitHub README 빌더 + 풀이 파일 push 헬퍼
│   └── review_response.py  # 리뷰 저장 + ReviewResponse 생성 (review/solved 공용)
│
└── static/
    ├── index.html
    ├── style.css
    └── js/                 # 각 파일이 하나의 UI 기능 담당
        ├── utils.js            # 공통 순수 함수
        ├── editor.js           # CodeMirror 에디터
        ├── theme.js            # 다크/라이트 테마
        ├── tabs.js             # 탭 전환 네비게이션
        ├── github.js           # GitHub OAuth 연결 UI
        ├── tier-chart.js       # 티어 변화 Chart.js 그래프
        ├── review.js           # 코드 리뷰 탭
        ├── recommend.js        # 문제 추천 탭
        ├── problem-modal.js    # CF 문제 뷰어 모달
        ├── stats.js            # 태그 통계 시각화
        ├── history.js          # 리뷰 기록 탭
        ├── report.js           # 종합 분석 리포트 탭
        ├── import-history.js   # import 기록 목록, 필터/페이징, AI 리뷰 요청
        ├── import-github.js    # BaekjoonHub import 버튼 핸들러
        ├── import-boj.js       # BOJ import 버튼 핸들러
        └── import-codeforces.js# CF import 버튼 핸들러
```

> 상세 레이어 다이어그램, 호출관계, 보안 조치 내역은 [ARCHITECTURE.md](./ARCHITECTURE.md)를 참조하세요.

## 기술 스택

- **Backend**: FastAPI + Uvicorn
- **Frontend**: HTML / CSS / Vanilla JS
- **AI**: OpenAI API (GPT-4o)
- **BOJ 데이터**: solved.ac API
- **Codeforces 데이터**: Codeforces API + 크롤링
- **DB**: SQLite (로컬 / 데모) / PostgreSQL (배포)
- **배포**: GCP Cloud Run

## 환경변수 전체 목록

| 변수 | 필수 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | GPT-4o 코드 리뷰 및 번역 |
| `GITHUB_CLIENT_ID` | 선택 | GitHub OAuth 앱 Client ID |
| `GITHUB_CLIENT_SECRET` | 선택 | GitHub OAuth 앱 Client Secret |
| `APP_URL` | 선택 | 서버 공개 URL (OAuth redirect 용) |
| `CODEFORCES_API_KEY` | 선택 | CF 소스코드 import용 |
| `CODEFORCES_API_SECRET` | 선택 | CF 소스코드 import용 |
| `OPENAI_MODEL` | 선택 | 사용할 OpenAI 모델 (기본값: `gpt-4o`) |
| `CORS_ORIGINS` | 선택 | 허용 CORS 출처 (기본값: `http://localhost:8080`) |
| `DEMO_MODE` | 선택 | `true` 설정 시 mock 데이터로 동작 (API 키 불필요) |
| `DB_TYPE` | 선택 | `postgres` 설정 시 PostgreSQL 사용 (기본: SQLite) |
| `DB_NAME` | 선택 | PostgreSQL DB 이름 |
| `DB_USER` | 선택 | PostgreSQL 사용자 |
| `DB_PASSWORD` | 선택 | PostgreSQL 비밀번호 |
| `DB_HOST` | 선택 | PostgreSQL 호스트 |
| `DB_PORT` | 선택 | PostgreSQL 포트 |
| `DB_SOCKET` | 선택 | Cloud SQL Unix socket 경로 |

## 라이선스

MIT
