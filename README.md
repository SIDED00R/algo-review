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
  - 리뷰 결과는 GitHub 저장소에 코드 + README(리뷰 섹션 포함)로 push 할 수 있습니다.
- **리뷰 없이 먼저 등록 → 나중에 AI 리뷰**
  - LLM 토큰이 없어 리뷰가 실패해도 코드와 문제 정보만으로 GitHub에 올릴 수 있습니다(`리뷰 대기` 상태로 기록).
  - 나중에 '리뷰 기록' 탭에서 AI 리뷰를 실행하면 같은 기록이 채워지고(제출 회차는 늘지 않음) README의 리뷰 섹션도 갱신됩니다.
  - 대기 상태는 태그 통계에 섞이지 않고, 실제 리뷰가 채워질 때 처음 집계됩니다.
- **CF 인앱 문제 뷰어**
  - Codeforces 문제를 앱 내에서 바로 보고 한국어 번역까지 제공합니다.
  - 예제 입출력 직접 실행 (Python / C++) 지원
- **기록 import**
  - `BaekjoonHub GitHub` 저장소 import
  - `BOJ 제출 기록` import
  - `Codeforces handle` 기반 import
- **지난 제출 불러오기 → 고쳐서 재제출**
  - 효율성 지적을 받은 코드를 리뷰 폼으로 다시 불러와 수정하고 재제출합니다. 새 제출은 회차로 쌓이고 과거 회차는 그대로 남습니다.
  - 코드 리뷰 탭의 `지난 제출 불러오기`(입력한 문제의 최신 회차) 또는 리뷰 기록 모달의 `이 코드로 다시 풀기`(원하는 회차)로 들어갑니다.
  - 코드·언어·문제 번호·문제 설명이 함께 복원됩니다.
- **명령 팔레트 (⌘K / Ctrl+K)**
  - 탭 이동과 지난 제출 불러오기를 한 곳에서 합니다. 문제 번호를 기억하지 못할 때 제목·태그로 검색해 회차를 골라 불러옵니다.
- **리뷰 기록 조회**
  - 문제별 제출 이력과 상세 피드백을 다시 확인할 수 있습니다. 회차는 제출 원장(날짜·시간복잡도·판정)으로 표시됩니다.
- **통계 / 리포트**
  - BOJ / Codeforces 플랫폼 전환 탭 제공
  - 태그 통계, 티어(레이팅) 변화, 누적 분석 리포트
- **문제 추천**
  - 약한 태그와 현재 수준 + 도전 난이도를 혼합해 다음 문제를 추천합니다.
  - BOJ / Codeforces 각각 지원
- **테마별 문제**
  - 사용자 데이터와 무관하게 알고리즘 분야별(DP·그리디·그래프 등 10개) 대표 문제를 플랫폼(Codeforces/백준) 토글 + 테마 칩으로 둘러봅니다.
  - 난이도는 사이트 네이티브 그대로 표시합니다 (CF: 레이팅 + 공식 색상 배지, 백준: solved.ac 실제 티어 배지). 이미 푼 문제는 목록에서 제외됩니다.
  - 백준 카드는 acmicpc 서비스 종료로 링크 없이 정보만 표시, CF 카드는 클릭 시 기존 인앱 뷰어 모달로 열립니다.

## 로컬 실행

### 1. 요구사항

- Python 3.13
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

`.env.example` 을 `.env` 로 복사해 값을 채웁니다 (전체 변수 목록·기본값은 `.env.example` 참고).

```bash
cp .env.example .env
```

필수 항목만 예시:

```env
OPENAI_API_KEY=your_openai_key
```

나머지 선택 항목(GitHub OAuth, Codeforces import, CORS, PostgreSQL 등)은 `.env.example` 참조.

### 4. 실행

```bash
python -m uvicorn server:app --reload --port 8080
```

브라우저에서 `http://localhost:8080` 접속 (CORS 기본 허용 출처·컨테이너 포트와 동일한 8080 사용)

헬스체크: `GET /health` → `{"status": "ok", "db": "ok"|"unavailable"}` (상태코드는 항상 200 — 온디맨드 DB 정지와 무관).

### 5. 테스트 / 린트 (개발)

```bash
pip install -r requirements-dev.txt
pytest          # DB 계층·라우트·마이그레이션·CF 본문 파싱 테스트 (기본 SQLite)
ruff check .    # 린트
```

CI(`.github/workflows/deploy.yml`)는 PR·push 마다 lint + test(SQLite/PostgreSQL 두 방언)를 돌리고, 통과해야 배포한다.

## Codeforces 관련 주의사항

- CF 문제 본문은 공식 API가 제공하지 않으므로 크롤링으로 가져옵니다.
  - 실패 시 리뷰 화면의 `문제 설명` 입력칸에 직접 붙여 넣어도 됩니다.
- CF 소스코드 import는 본인 계정 API Key / Secret이 필요합니다.

## 배포

### 자동 배포 (CI/CD)

`main` 브랜치에 머지되면 GitHub Actions(`.github/workflows/deploy.yml`)가 Cloud Run 두 서비스(`algo-review`, `algo-review-demo`)에 자동 배포합니다. 아래 명령들은 수동 배포가 필요할 때 사용합니다.

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
├── analyzer.py             # OpenAI GPT 코드 분석
├── recommender.py          # 취약 태그 기반 문제 추천 알고리즘
├── themes.py               # 테마별 대표 문제 풀 조회 (플랫폼별 네이티브 난이도) + DB 캐시
├── cf_translator.py        # OpenAI를 이용한 CF 문제 본문 한국어 번역
├── demo_mode.py            # 데모 모드 플래그 및 mock 데이터
├── demo_seed.py            # 데모용 SQLite 샘플 데이터 시딩
├── warmup.py               # 기동 직후 테마 캐시 백그라운드 예열
├── ARCHITECTURE.md         # 레이어 다이어그램 & 호출관계 문서
├── requirements.txt        # Python 의존성
├── requirements-dev.txt    # 개발용 의존성 (pytest, ruff 등)
├── pyproject.toml          # ruff·pytest 설정
├── alembic.ini             # Alembic 설정
├── .env.example            # 환경변수 템플릿
├── Dockerfile              # Cloud Run 컨테이너 이미지 (uvicorn, 8080 포트)
├── .dockerignore
├── .github/workflows/deploy.yml  # main 머지 시 Cloud Run 자동 배포 (prod + demo)
├── LICENSE                 # MIT
├── assets/                 # 데모 GIF (미사용)
│
├── clients/                # 외부 API 클라이언트 (플랫폼별 분리) — 파일별 책임은 ARCHITECTURE.md 참조
│
├── config.py               # 환경변수 → SQLAlchemy 접속 URL (pydantic-settings)
├── db/                     # DB 레이어 (SQLAlchemy 2.0 ORM) — 파일별 책임은 ARCHITECTURE.md 참조
├── migrations/             # Alembic (env.py + versions/)
│
├── routes/                 # FastAPI 라우터 (도메인별 분리) — 엔드포인트 목록은 ARCHITECTURE.md 참조
│
├── tests/                  # pytest (DB 계층·라우트·마이그레이션·CF 본문 파싱)
│
└── static/
    ├── index.html          # SPA 셸 (탭 7개 + 모달 2개 + 아이콘 SVG 스프라이트)
    ├── css/                # 책임별 5개 — 파일별 책임은 ARCHITECTURE.md 참조
    └── js/                 # UI 기능별 모듈 17개 — 파일별 책임은 ARCHITECTURE.md 참조
```

> 파일별 단일 책임, 엔드포인트 목록, 레이어 다이어그램, 호출관계, 보안 조치 내역은
> [ARCHITECTURE.md](./ARCHITECTURE.md)를 참조하세요.

## 기술 스택

- **Backend**: FastAPI + Uvicorn
- **Frontend**: HTML / CSS / Vanilla JS
- **AI**: OpenAI API (코드 리뷰·리포트: GPT-4o, CF 문제 번역: GPT-4o-mini)
- **BOJ 데이터**: solved.ac API
- **Codeforces 데이터**: Codeforces API + 크롤링
- **DB**: SQLAlchemy 2.0 ORM + Alembic 마이그레이션 — SQLite (로컬 / 데모) / PostgreSQL (배포)
- **배포**: GCP Cloud Run

## 환경변수 전체 목록

| 변수 | 필수 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | AI 코드 리뷰·리포트 및 CF 문제 번역 |
| `GITHUB_CLIENT_ID` | 선택 | GitHub OAuth 앱 Client ID |
| `GITHUB_CLIENT_SECRET` | 선택 | GitHub OAuth 앱 Client Secret |
| `APP_URL` | 선택 | 서버 공개 URL (OAuth redirect 용) |
| `CODEFORCES_API_KEY` | 선택 | CF 소스코드 import용 |
| `CODEFORCES_API_SECRET` | 선택 | CF 소스코드 import용 |
| `OPENAI_MODEL` | 선택 | 사용할 OpenAI 모델 — 미설정 시 리뷰·리포트 `gpt-4o`, 번역 `gpt-4o-mini`. 설정하면 리뷰·번역 모두 이 값으로 대체 |
| `OPENAI_BASE_URL` | 선택 | OpenAI 호환 엔드포인트 URL — 다른 제공자(예: Gemini)로 전환할 때만 지정 |
| `OPENAI_MAX_TOKENS` | 선택 | 리뷰·번역 응답 최대 토큰 (기본값: 리뷰 `2048`, 번역 `2000`) |
| `OPENAI_REPORT_MAX_TOKENS` | 선택 | 종합 리포트 응답 최대 토큰 (기본값: `1024`) |
| `OPENAI_TEMPERATURE` | 선택 | CF 번역 temperature (기본값: `0.3`) |
| `OPENAI_TIMEOUT` | 선택 | LLM 호출(리뷰·리포트·CF 번역) 공통 타임아웃(초) (기본값: `15`) |
| `COMPILE_TIMEOUT` | 선택 | `/api/execute` C++ 컴파일 타임아웃(초) (기본값: `30`) |
| `CORS_ORIGINS` | 선택 | 허용 CORS 출처 (기본값: `http://localhost:8080`) |
| `DEMO_MODE` | 선택 | `true` 설정 시 mock 데이터로 동작 (API 키 불필요) |
| `DATABASE_URL` | 선택 | SQLAlchemy 접속 URL 직접 지정 (설정 시 아래 `DB_*` 무시) |
| `DB_TYPE` | 선택 | `postgres` 설정 시 PostgreSQL 사용 (기본: SQLite) |
| `DB_PATH` | 선택 | SQLite 파일 경로 (기본값: 프로젝트 루트 `coding_recommend.db`) |
| `DB_NAME` | 선택 | PostgreSQL DB 이름 |
| `DB_USER` | 선택 | PostgreSQL 사용자 |
| `DB_PASSWORD` | 선택 | PostgreSQL 비밀번호 |
| `DB_HOST` | 선택 | PostgreSQL 호스트 |
| `DB_PORT` | 선택 | PostgreSQL 포트 |
| `DB_SOCKET` | 선택 | Cloud SQL Unix socket 경로 |

## 라이선스

MIT
