# Architecture

## 레이어 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (static/js/*.js — 20개)                                │
│  editor · utils · theme · github · tier-chart · tabs            │
│  review · recommend · themes · problem-modal · stats            │
│  history · report · load-submission · command-palette           │
│  modal-a11y                                                     │
│  import-history · import-github · import-codeforces             │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP (fetch)
┌────────────────────────▼────────────────────────────────────────┐
│  FastAPI Routes (routes/)                                       │
│  auth · review · pending_review · rereview · github_push        │
│  problem · execute · recommend · themes · history · solved      │
│  stats · report · import_github · import_codeforces             │
└────────┬───────────────────────────────┬───────────────────────┘
         │                               │
┌────────▼────────┐             ┌────────▼─────────────────────────┐
│  Service Layer  │             │  External Clients (clients/)      │
│  analyzer.py    │             │  solved_ac · codeforces           │
│  recommender.py │             │  github · utils                   │
│ cf_translator.py│             └──────────────┬────────────────────┘
│  themes.py      │                            │
└────────┬────────┘                            │
         │                                     │ HTTP
┌────────▼────────────────────┐       ┌────────▼─────────────────────────┐
│  DB Layer (db/) — SQLAlchemy │       │  External APIs                   │
│  models · connection         │       │  solved.ac · Codeforces          │
│  reviews · solved · cache    │       │  GitHub · OpenAI                 │
│  github_settings · migrate   │       └──────────────────────────────────┘
│  normalize · paging          │
└────────┬────────────────────┘
         │   (단순 상수는 constants.py — 레이어 간 상호 import 없이 어느 쪽에서도 참조)
         │
┌────────▼──────────────────────┐
│  SQLite / PostgreSQL          │   (스키마: Alembic 마이그레이션)
└───────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  warmup.py — server.py lifespan 기동 시 백그라운드 태스크로 실행     │
│  themes.py: 신선하지 않은 플랫폼×테마만 골라 문제 풀 캐시 예열      │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  executor/ — 별도 Cloud Run 서비스 (algo-executor)                 │
│  routes/execute.py 가 ID 토큰을 붙여 POST /run 으로 위임한다        │
│  main.py: HTTP 경계 · runner.py: 자식 프로세스 실행 + 자원 상한     │
│  앱 코드·DB·시크릿 없음 / 권한 0 SA / 외부 통신 차단                │
└───────────────────────────────────────────────────────────────────┘
```

---

## 파일 책임 목록

### 서버 진입점
| 파일 | 단일 책임 |
|------|----------|
| `server.py` | FastAPI 앱 초기화, 미들웨어·라우터 등록, `lifespan`으로 DB 마이그레이션/데모 시드 + 테마 캐시 예열 기동, `GET /`(index.html 서빙 + `__V__` 자산 캐시 버전 치환), `GET /health`, 전역 예외 핸들러 |
| `config.py` | 모든 환경변수를 읽는 중앙 설정(pydantic-settings) — DB URL + OpenAI/GitHub/CF/CORS 등 |
| `constants.py` | 플랫폼 화이트리스트·티어 이름·`normalize_platform()` — 레이어 어디서나 참조하는 순수 값. `clients` 에 두면 `import db` 만 해도 `requests`·`bs4` 가 함께 로드되는 레이어 역의존이 생긴다 |
| `llm_client.py` | OpenAI 호환 클라이언트 싱글턴 + 응답 가드 — LLM 을 부르는 모듈(`analyzer`·`cf_translator`)이 공유한다. 호출마다 클라이언트를 만들면 httpx 커넥션 풀과 TLS 핸드셰이크를 매번 버리고, `max_retries` 를 안 박으면 실효 상한이 3×timeout + 백오프가 된다 |
| `warmup.py` | 기동 직후 백그라운드로 플랫폼×테마 문제 풀 캐시 예열 |
| `timestamps.py` | 저장 시각의 단일 규약 — 항상 오프셋 있는 UTC 로 저장(`utc_now_iso`), 읽을 때 오프셋 없는 값은 UTC 로 해석(`parse_stored`) |
| `backfill_statements.py` | 기존 기록의 `problem_statement` 백필(일회성 CLI). BOJ 는 GitHub README, CF 는 codeforces.com 재수집. dry-run 기본, `--apply` 로만 기록 |

### 서비스 레이어
| 파일 | 단일 책임 |
|------|----------|
| `analyzer.py` | LLM 코드 분석 + 응답 파싱(`parse_review_json`)·정규화(`normalize_review_result`). 클라이언트는 `llm_client` 를 쓴다 |
| `recommender.py` | 취약 태그 기반 문제 추천 알고리즘 |
| `themes.py` | 테마(알고리즘 분야)별 플랫폼별(CF/백준) 대표 문제 풀 조회, 네이티브 난이도 밴드 분류 + DB 캐시 |
| `cf_translator.py` | Codeforces 문제 본문 한국어 번역. `llm_client` 를 쓴다 — 문제 뷰어는 한 요청에 섹션 4개를 동시 번역하므로 싱글턴의 근거가 가장 큰 곳이다 |

### 데모 인프라
| 파일 | 단일 책임 |
|------|----------|
| `demo_mode.py` | 데모 모드 플래그(`IS_DEMO`)와 라우터가 반환하는 mock 응답 데이터 |
| `demo_seed.py` | 데모 서버 기동 시 SQLite 샘플 데이터 시딩 |

### 실행 전용 서비스 (`executor/`)
앱과 **다른 Cloud Run 서비스**로 배포한다(`--source executor`). 앱 모듈을 import 하지 않는다 —
이미지에 앱 코드가 들어가지 않기 때문이다. 로컬 개발에서는 `routes/execute.py` 가 `runner` 를
직접 import 해 같은 구현을 쓴다.

| 파일 | 단일 책임 |
|------|----------|
| `executor/main.py` | HTTP 경계(`POST /run`, `GET /health`)와 요청 상한 재검증 — 호출자를 믿지 않는다 |
| `executor/runner.py` | 자식 프로세스 실행(Python/C++)과 자원 상한(출력·stdin·시간·프로세스 그룹 종료) |

### DB 레이어 (`db/`)
SQLAlchemy 2.0 ORM 을 쓴다. SQLite(로컬/데모) ↔ PostgreSQL(운영) 은 접속 URL 만 다르고
쿼리 코드는 단일 경로다(수동 방언 분기 없음). 스키마는 Alembic 으로 버전 관리한다.

| 파일 | 단일 책임 |
|------|----------|
| `db/models.py` | ORM 모델 6개(Review·TagStat·SolvedHistory·GithubSetting·ApiCache·CodeDraft) + 인덱스. `reviews.problem_statement` 는 불러오기로 폼을 복원할 때 쓰는, 사용자가 붙여 넣은 원문이다 |
| `db/connection.py` | 지연 엔진 싱글턴(`get_engine`)·세션 컨텍스트(`session_scope`)·`dispose_engine` |
| `db/migrate.py` | 프로그래매틱 Alembic `upgrade head` 실행(`run_migrations`) |
| `db/normalize.py` | reviews/solved 행 정규화 공용 헬퍼 (platform·problem_ref·tags·tier_name 폴백) |
| `db/reviews.py` | reviews 테이블 CRUD + 티어/태그 집계 쿼리 + 리뷰 대기 마커(`PENDING_EFFICIENCY`) 처리 |
| `db/solved.py` | solved_history 테이블 CRUD |
| `db/github_settings.py` | github_settings 테이블 CRUD |
| `db/cache.py` | api_cache 테이블 CRUD — 외부 API 파생 페이로드 TTL 캐시 (`cache_get`/`cache_get_stale`/`cache_set`) |
| `db/drafts.py` | code_drafts 테이블 CRUD — 에디터 임시 저장본. 키 하나가 에디터 자리 하나다(`main` · `codeforces:{ref}`). 빈 코드는 저장하지 않고 행을 지운다 |
| `db/__init__.py` | 패키지 외부(라우터·서비스)에서 사용하는 함수 re-export |
| `db/paging.py` | 목록 API 페이지네이션 경계(`paging_bounds`, 상한 100)와 검색 술어(`search_filter`) — 리뷰 기록·가져온 기록 공용 |
| `migrations/` | Alembic 환경(`env.py`) + 리비전(`versions/`) |

### 외부 클라이언트 레이어 (`clients/`)
| 파일 | 단일 책임 |
|------|----------|
| `clients/solved_ac.py` | solved.ac API, BOJ 스크래핑. `TIER_NAMES` 의 정본은 `constants.py` 다. `get_boj_problem_sections()` 는 실패 시 `None` — CF 쌍둥이 함수와 같은 계약이다 |
| `clients/codeforces.py` | Codeforces API, 문제 메타/본문 스크래핑 |
| `clients/github.py` | GitHub OAuth, 파일 push, BaekjoonHub import, 저장소 트리 조회(`fetch_repo_tree`·`get_boj_readme_paths`) |
| `clients/utils.py` | `get_problem_url()`, 파일 확장자 매핑(`get_file_extension`), 브라우저 UA 단일 출처(`BROWSER_USER_AGENT` — solved.ac·CF 헤더가 공유), 예외 두 종 — `ProblemSearchError`(검색 **실패**를 빈 결과와 구분) · `UpstreamUnavailable`(외부 서비스 **도달 실패**를 입력 오류와 구분; `ValueError` 를 상속해 기존 핸들러를 깨지 않는다) |
| `clients/__init__.py` | 패키지 외부(라우터·서비스)에서 사용하는 함수 re-export |

### API 라우터 (`routes/`)
| 파일 | 엔드포인트 | 단일 책임 |
|------|-----------|----------|
| `routes/auth.py` | `/auth/github/*` | GitHub OAuth 인증 흐름 |
| `routes/review.py` | `POST /api/review` | AI 코드 리뷰 생성 |
| `routes/pending_review.py` | `POST /api/review/pending` | LLM 없이 코드+문제 정보만 push 하고 '리뷰 대기'로 기록 |
| `routes/rereview.py` | `POST /api/rereview/{platform}/{ref}` | 대기 행을 AI 리뷰로 채우고(회차 증가 없음) README 갱신 |
| `routes/github_push.py` | `POST /api/push-review` | GitHub 저장소에 코드+README push (최신 리뷰 내용 포함) |
| `routes/problem_resolve.py` | — | 문제 식별자 → 문제 메타/본문 해석 (review·pending·rereview 공용). `is_scrape_failure()` 로 수집 실패 문자열을 걸러 LLM 프롬프트에 들어가지 않게 한다 |
| `routes/problem.py` | `GET /api/problem/cf/{ref}` | CF 문제 조회 라우트 + 응답 캐시 |
| `routes/execute.py` | `POST /api/execute` | Python/C++ 코드 실행을 실행 전용 서비스로 **위임**(`EXECUTOR_URL`) + IP 레이트리밋. `EXECUTOR_URL` 이 없으면 403 — 앱은 어떤 경로로도 직접 실행하지 않는다 |
| `routes/recommend.py` | `GET /api/recommend` | 문제 추천 API |
| `routes/themes.py` | `GET /api/themes`, `GET /api/themes/{theme_id}/problems` | 테마 목록 + 플랫폼별 테마 문제 조회 (푼 문제 제외) |
| `routes/drafts.py` | `GET /api/drafts/{key}`, `POST /api/drafts/{key}` | 에디터 임시 저장본 조회/저장. 없는 저장본은 404 가 아니라 빈 값이다 — 프론트가 '아직 없음' 과 '조회 실패' 를 구분해야 한다 |
| `routes/history.py` | `GET /api/reviews/grouped`, `GET /api/reviews/problem/{platform}/{ref}` | 리뷰 기록 조회 |
| `routes/solved.py` | `/api/solved-history/*`, `POST /api/review-imported/*` | 가져온 기록 관리 + AI 리뷰 요청 |
| `routes/stats.py` | `GET /api/stats`, `GET /api/tier-history` | 통계 및 티어 이력 조회 |
| `routes/report.py` | `GET /api/report` | 종합 분석 리포트 생성 |
| `routes/import_github.py` | `POST /api/import-github` | BaekjoonHub 저장소 가져오기 |
| `routes/import_codeforces.py` | `POST /api/import-codeforces` | Codeforces 제출 기록 가져오기 |
| `routes/models.py` | — | Pydantic 요청/응답 스키마 |
| `routes/helpers.py` | — | GitHub push 공용 헬퍼 (README 빌더 + 리뷰 섹션, 저장 폴더·커밋 메시지 조립, 설정+override 병합, README+코드 번들 push) · 요청 검증(`require_platform`·`require_language`·`require_reviewable_code`) · 상류 실패 매핑(`upstream_failure`·`run_llm`) · LLM 전제 검사(`require_openai_key`) · 평균 난이도 표기(`average_difficulty`) |
| `routes/review_response.py` | — | 리뷰 저장 + ReviewResponse 생성 (review/solved 공용) |

### 프론트엔드 스타일 (`static/css/`)
순수 CSS 5개. 빌드 스텝이 없으므로 `index.html` 의 로드 순서가 곧 캐스케이드 순서다 —
서드파티(CodeMirror·KaTeX) CSS 를 먼저 걸고 앱 CSS 를 뒤에 두어야 오버라이드가 이긴다.

| 파일 | 단일 책임 |
|------|----------|
| `css/tokens.css` | 리셋 + 디자인 토큰. 크롬은 무채색이고 유채색은 데이터(티어·CF 등급·효율 판정)에만 쓴다는 규칙의 정의 지점. 데이터 색 32쌍은 테마별 전경/배경/경계를 짝으로 두고 전부 4.5:1 이상을 만족한다 |
| `css/base.css` | 요소 기본값, 타이포 스케일, 전역 `:focus-visible` 링, `prefers-reduced-motion` |
| `css/components.css` | 버튼·폼·배지·태그·알림·스피너·코드블록·표·제출 원장(`.ledger`)·페이지네이션 |
| `css/layout.css` | 헤더/탭바, 콘텐츠 성격별 컨테이너 3종(`.measure-work` / `.measure-list` / `.measure-prose`), 목록 행, 반응형 |
| `css/surfaces.css` | 모달·오버레이·드롭다운·문제 풀기 모달·CodeMirror 오버라이드 |

### 프론트엔드 (`static/js/`)
| 파일 | 단일 책임 |
|------|----------|
| `utils.js` | 공통 유틸 — 순수 함수(tierClass, cfRatingClass, tierBadgeHtml, escapeHtml, detectLanguage 등) + fetch 골격(fetchJsonOk) |
| `editor.js` | CodeMirror 에디터 초기화 및 관리 |
| `load-submission.js` | 지난 제출을 리뷰 폼에 채워 편집 가능한 상태로 만든다. 진입점 넷(메인 탭 버튼·리뷰 기록 모달·⌘K 팔레트·문제 풀기 모달의 '코드 리뷰 진행')이 이 파일의 `fillReviewForm` 을 쓴다 |
| `command-palette.js` | ⌘K 팔레트 — 탭 이동 + 문제 검색 → 회차 선택 → 불러오기 |
| `theme.js` | 다크/라이트 테마 토글 (`html[data-theme]`). 첫 페인트 전 확정은 `index.html` `<head>` 인라인 스크립트가 담당 |
| `github.js` | GitHub OAuth 연결 UI |
| `tabs.js` | 탭 전환 네비게이션. `activateTab(name)` 이 유일한 전환 경로다 — 탭별 lazy loader 와 모바일 메뉴 닫기를 반드시 통과한다 |
| `modal-a11y.js` | 모달 접근성 공통 — Esc 닫기·포커스 트랩·초기 포커스·복원을 `registerModal()` 한 곳에서 등록한다. 모달마다 복제하면 새 모달에서 또 빠진다. `escapeCloses: false` 는 Esc 닫기만 끈다(에디터가 든 모달용) |
| `draft.js` | 에디터 임시 저장 — 디바운스 자동 저장·복원·'임시 저장' 버튼. 메인 리뷰 탭은 로드 시 `main` 에 붙고, 문제 뷰어는 열 때 `codeforces:{ref}` 에 붙는다 |
| `review.js` | 코드 리뷰 제출 및 결과 표시 |
| `recommend.js` | 문제 추천 표시 |
| `themes.js` | 테마별 문제 탭 — 플랫폼 토글, 테마 칩, 3계층 캐시(메모리/localStorage/서버), 유휴 프리페치 |
| `problem-modal.js` | CF 문제 모달 (조회, 샘플 실행, 리뷰 이동) |
| `stats.js` | 태그 통계 시각화 |
| `tier-chart.js` | 티어 변화 Chart.js 그래프. 색은 CSS 변수에서 읽고 `data-theme` 변경을 감시해 재렌더한다 |
| `history.js` | 리뷰 기록 목록 및 상세 모달 |
| `report.js` | 종합 분석 리포트 표시 |
| `import-history.js` | 가져온 기록 목록 표시, 필터/페이징, 코드 보기, AI 리뷰 요청 |
| `import-github.js` | BaekjoonHub GitHub import 버튼 핸들러 |
| `import-codeforces.js` | Codeforces import 버튼 핸들러 |

---

## 주요 호출 관계

| Caller | Callee | 목적 |
|--------|--------|------|
| `server.py` | `db.run_migrations` | lifespan 기동 시 Alembic `upgrade head` |
| `server.py` | `warmup.warm_theme_caches` | lifespan 기동 시 테마 캐시 예열 백그라운드 태스크 시작 (데모 제외) |
| `warmup.py` | `themes.theme_pool_is_fresh` · `themes.get_theme_problem_pool` | 플랫폼×테마를 돌며 신선도를 먼저 보고 **신선하지 않은 것만** 예열한다. 하루 첫 인스턴스 외에는 외부 호출이 0이다 |
| `routes/problem_resolve.py` | `clients.get_codeforces_problem_info` | CF 문제 메타데이터 조회 |
| `routes/problem_resolve.py` | `clients.get_problem_info` | BOJ 문제 메타데이터 조회 |
| `routes/review.py` | `analyzer.analyze_code` | LLM 코드 분석 (모델은 `OPENAI_MODEL`, 기본 gpt-4o — `.env.example` 은 Gemini 호환 엔드포인트도 안내한다) |
| `routes/review.py` | `db.save_review` | 리뷰 결과 저장 |
| `routes/pending_review.py` | `db.save_review` | 리뷰 대기 행 저장 (push 성공 후에만) |
| `routes/rereview.py` | `analyzer.analyze_code` | 대기 행 재리뷰 — LLM 을 호출하는 두 번째 경로 |
| `routes/rereview.py` | `db.update_pending_review` | 대기 행을 리뷰 결과로 갱신 + 태그 통계 첫 집계 |
| `routes/helpers.py` | `clients.push_files_to_github` | 코드+README 단일 커밋 GitHub push |
| `routes/problem.py` | `clients.scrape_cf_problem` | CF 문제 본문 스크래핑 |
| `routes/problem.py` | `cf_translator.translate_cf_text` | CF 본문 OpenAI 한국어 번역 |
| `routes/helpers.py` | `clients.tex_markers_to_markdown` | README push 시 수식 이미지 마커 → 마크다운 |
| `routes/execute.py` | 실행 전용 서비스 POST /run | ID 토큰을 붙여 코드 실행을 위임(EXECUTOR_URL) |
| `routes/stats.py`·`routes/recommend.py` | `helpers.average_difficulty` | 평균 난이도 조회 + 표시 라벨(내부에서 `db.get_average_tier`/`get_average_cf_rating`) |
| `routes/report.py` | `analyzer.get_cumulative_analysis` | LLM 종합 리포트 생성 |
| `routes/import_github.py` | `clients.get_baekjoonhub_problems` | BaekjoonHub 저장소 트리 파싱 |
| `routes/import_github.py` | `clients.get_problems_bulk` | 대량 문제 정보 조회 |
| `routes/import_codeforces.py` | `clients.get_codeforces_user_submissions` | CF 제출 기록 조회 |
| `routes/themes.py` | `themes.build_theme_response` | 플랫폼별 테마 문제 풀에서 푼 문제 제외 후 응답 생성 |
| `themes.py` | `clients.search_cf_problems_by_tag` | 테마(CF 태그)별 대표 문제 풀 조회 |
| `themes.py` | `clients.search_problems_by_tag` | 테마(solved.ac 태그)별 대표 문제 풀 조회 |
| `themes.py` | `db.cache_get` / `db.cache_set` / `db.cache_get_stale` | 테마 문제 풀 DB 캐시 조회/저장, 외부 API 실패 시 만료 캐시 폴백 |
| `recommender.py` | `db.get_tag_weakness_data` | 태그 취약점 점수 데이터 조회 |
| `recommender.py` | `clients.search_problems_by_tag` | solved.ac 태그 검색 |
| `routes/auth.py` | `clients.exchange_github_code` | GitHub OAuth 토큰 교환 |
| `routes/auth.py` | `db.save_github_settings` | GitHub 토큰 저장 |
| `problem-modal.js` | `GET /api/problem/cf/{ref}` | CF 문제 내용 조회 |
| `problem-modal.js` | `POST /api/execute` | 샘플 테스트 코드 실행 |
| `review.js` | `POST /api/review` | AI 코드 리뷰 요청 |
| `review.js` | `POST /api/review/pending` | 리뷰 실패 시 리뷰 없이 GitHub 등록 |
| `history.js` | `POST /api/rereview/{platform}/{ref}` | 대기 기록의 AI 리뷰 실행 + README 갱신 |
| `recommend.js` | `GET /api/recommend` | 문제 추천 요청 |
| `themes.js` | `GET /api/themes` | 테마 목록 요청 (localStorage 24h 캐시) |
| `themes.js` | `GET /api/themes/{theme_id}/problems` | 플랫폼별 테마 문제 요청 (메모리/localStorage 30분 캐시) |
| `import-history.js` | `GET /api/solved-history` | 가져온 기록 목록 조회 |
| `load-submission.js` | `GET /api/reviews/problem/{platform}/{ref}` | 지난 제출 코드·언어·문제 설명 조회 |
| `command-palette.js` | `GET /api/reviews/grouped` | 팔레트 문제 검색 목록 |
| `draft.js` | `GET /api/drafts/{key}` · `POST /api/drafts/{key}` | 임시 저장본 복원 / 자동·수동 저장 |

---

## 보안 경계

| # | 위치 | 무엇을 막는가 |
|---|------|----------|
| 1 | `routes/execute.py` · `executor/` | 임의 코드 실행을 **앱 밖으로 분리**했다. 앱은 실행하지 않고 `EXECUTOR_URL` 로 위임한다. 앱 프로세스 안에서 돌리면 `_SAFE_ENV_KEYS` 필터·`cwd` 격리·`-I` 를 다 걸어도 ① 네트워크 egress → GCE 메타데이터 서버 → 런타임 SA 토큰, ② `/proc/1/environ` → 앱 환경변수 전체(`USER` 가 `CMD` 앞이라 uvicorn 도 같은 uid 로 뜬다)가 남고, 둘 다 컨테이너 안에선 막을 수 없다(네트워크 차단은 `NET_ADMIN` 필수). 그래서 신뢰 경계를 밖에 세웠다 — 아래 11번. `EXECUTOR_URL` 이 없으면 `/api/execute` 는 403 이다. `tests/test_execute_isolation.py`(게이트·격리) 와 `tests/test_execute_delegation.py`(위임 배선) 가 함께 고정 |
| 2 | `db/` | 쿼리는 SQLAlchemy ORM 으로만 만든다 — 전부 파라미터 바인딩되어 SQL injection 표면이 없다 |
| 3 | `routes/auth.py` | OAuth 실패 시 예외 메시지 redirect URL 노출 제거, 서버 로그만 기록 |
| 4 | `server.py` | `CORSMiddleware` 추가 (환경변수 `CORS_ORIGINS`로 허용 출처 설정) |
| 5 | `server.py` | 전역 예외 핸들러 — DB 연결 실패(`OperationalError`)는 503 + 안내, 그 외 미처리 예외는 500 generic(내부 상세 비노출) + traceback 로깅 |
| 6 | `routes/models.py` | `ExecuteRequest` validator: 코드 50,000자, 입력 10,000자, timeout 1~10초 제한 |
| 7 | `.github/workflows/deploy.yml` | 접근 정책을 **코드가 정본**으로 갖는다 — 앱·데모는 `--allow-unauthenticated`(공개 운영 결정), 실행 서비스만 `--no-allow-unauthenticated`. 명시하지 않으면 배포가 기존 IAM 을 "보존" 하므로, 콘솔에서 바뀐 상태가 배포로 되돌아가지 않는다 |
| 8 | `routes/helpers.py` | `merged_github_target` 은 저장소·토큰을 **짝으로만** 받는다. 한쪽만 override 하면 나머지가 저장된 값으로 폴백해, 요청자가 고른 저장소에 저장된 토큰(`scope=repo`)으로 커밋된다 |
| 9 | `routes/models.py` | `PushReviewRequest` 의 경로·README 로 나가는 필드에 상한 — title/tier_name/language 200자, tags 30개×100자, url 은 `http(s)` 500자. 없으면 요청 1건으로 수 MB README 를 커밋하거나 경로 길이 한계를 넘긴다 |
| 11 | `executor/` · `.github/workflows/deploy.yml` | 실행 전용 Cloud Run 서비스 `algo-executor`. 이미지에 앱 코드·DB·시크릿이 없고(`--clear-env-vars`), 런타임 SA `algo-executor-run` 에는 **IAM 역할이 하나도 없다** — 제출 코드가 메타데이터 서버에서 토큰을 받아도 그 토큰으로 할 수 있는 일이 없다. NAT 없는 서브넷으로 Direct VPC egress(`--vpc-egress all-traffic`)를 걸어 외부 통신을 끊고, `--no-allow-unauthenticated` + 앱 SA 에만 `run.invoker` 로 호출자를 앱으로 제한한다 |
| 12 | `executor/runner.py` | 실행 자원 상한 — 스트림당 출력 64KB(넘는 바이트는 읽어서 버린다: 파이프를 비워야 자식이 막히지 않는다), stdin 64KB, 실행 10초, 그리고 **프로세스 그룹째 종료**(`start_new_session` + `killpg`). 직접 자식만 죽이면 제출 코드가 남긴 손자가 인스턴스 수명 동안 CPU 를 계속 쓴다. `tests/test_executor_runner.py` 가 넷을 실측으로 고정 |
| 13 | `routes/execute.py` | `/api/execute` 는 인증이 없는 공개 엔드포인트다 — `X-Forwarded-For` 첫 항목 당 분당 30회로 제한한다(`request.client` 는 GFE 다). Cloud Run 은 클라이언트가 보낸 `X-Forwarded-For` 를 버리지 않으므로 이 키는 요청자가 정할 수 있다 — 그래서 헤더가 무엇이든 성립하는 전역 분당 120회 상한을 함께 건다. 실행 서비스의 `--max-instances 5` 가 비용 상한이고, 이 전역 상한이 그 비용 상한을 지킨다 |

### 남아 있는 위험 — 앱에 인증이 없다

이 앱에는 로그인·세션·사용자 구분이 **없다**(`Depends`/`Security` 사용 0건). 그런데 사용자의
GitHub OAuth 토큰(`scope=repo`)을 DB 에 저장하고 공개 엔드포인트가 그 토큰으로 커밋한다.

따라서 **서비스에 접근할 수 있는 사람 = 그 토큰을 쓸 수 있는 사람**이다. 접근 통제를 앱이
아니라 **Cloud Run IAM** 이 담당한다(위 7번). 운영 서비스는 현재 공개이므로 URL 을 아는
누구나 아래를 할 수 있다:

- `GET /auth/github/repos` — 비공개 저장소 이름 전량 조회
- `POST /api/push-review` · `/api/import-codeforces` — 저장된 토큰으로 임의 저장소에 커밋
- `DELETE /auth/github` · `POST /auth/github/repo` — 연결 해제 / 대상 저장소 변경
- `GET /api/reviews/problem/...` — 저장된 소스코드·리뷰 전문 열람
- `/api/report` · `/api/problem/cf/...` — 무제한 유료 LLM 호출
- `DELETE /api/solved-history` — 가져온 기록 전량 삭제
- `GET`·`POST /api/drafts/{key}` — 작성 중인 코드 열람·덮어쓰기(빈 코드로 삭제)

데모 서비스는 공개로 두어도 된다 — `DEMO_MODE` 가 과금·코드 실행·GitHub 접근을 차단하고
DB 가 컨테이너 임시 파일이다. DB 쓰기 자체는 열려 있다(리뷰 저장·임시 저장) — 그 임시 파일
안에서 끝나고 방문자끼리 공유된다.


---

## 조용한 오답이 나는 지점

테스트가 없으면 잡히지 않고, 실패하지도 않으면서 결과만 틀리는 곳이다.

| 지점 | 내용 | 방어 |
|------|------|------|
| `routes/problem_resolve.py` `resolve_statement` | 요청에 `problem_statement` 가 있으면 **무조건** 그것을 쓴다. 이전 문제의 붙여넣은 본문이 폼에 남아 있으면 다른 문제를 그 본문으로 리뷰한다 | `load-submission.js` 가 값이 없어도 `''` 를 조건 없이 대입한다. `tests/test_load_submission_wiring.py` 가 이 코드의 존재를 고정 |
| `reviews.language` | 자유 문자열이다 — import 경로가 CF/BOJ 원문(`"GNU G++17 7.3.0"`)을 그대로 저장한다. `select.value` 에 없는 값을 넣으면 조용히 실패해 빈 select 가 된다 | `submissionLanguageOption()` 이 option 존재를 확인하고, 없으면 `detectLanguage(code)` 로 재추론한다(반환 도메인이 option value 와 같다) |
| 탭 전환 | 전환 로직을 복제하면 탭별 lazy loader 와 모바일 메뉴 닫기를 건너뛴다 | `activateTab()` 한 곳만 둔다. 배선 테스트가 다른 JS 에 `.tab-content` 토글이 없음을 확인 |
| 본문 수집 함수 | `get_problem_statement()`·`get_codeforces_problem_statement()` 는 예외를 던지지 않고 **실패 문자열**을 반환한다. 그대로 넘기면 프롬프트의 문제 설명 자리에 `"크롤링 실패: 404 …"` 가 들어간다. BOJ 는 acmicpc.net 종료로 수집이 상시 실패한다 | LLM 에 본문을 넘기는 **세 경로 전부**(`review`·`rereview`·`review-imported`)가 `resolve_statement()` 를 쓴다 — `is_scrape_failure()` 로 걸러 빈 본문을 준다. 백필도 저장 직전에 같은 검사를 한다(저장하면 그 문제의 리뷰가 영구히 오염된다). **수집 함수를 직접 부르는 경로를 새로 만들면 안 된다** — 그 경로는 이 필터를 우회한다 |
| BOJ README 경로 |  저장소 폴더명은 BaekjoonHub 규칙이라 공백이 `U+2005`, 특수문자가 전각(`A＋B`)이고 `번` 이 없다. 티어 폴더도 저장 당시 값이라 DB 와 다르다(acmicpc 종료 후 조회 실패로 `Unrated` 인 행이 많다) → 경로를 조립하면 거의 다 404 다 | `get_boj_readme_paths()` 로 트리를 한 번 받아 번호로 찾는다. 번호 경계를 느슨하게 보면 `2024 대회 후기` 를 2024번 문제로 오인한다 |
| BOJ README 재푸시 | 수집 실패를 빈 섹션으로 오인하면 본문 없는 README 로 덮어써 **이미 올라간 문제 설명이 지워진다** | 두 겹으로 막는다 — ① `get_boj_problem_sections()` 가 `get_cf_problem_sections()` 와 같은 계약으로 실패 시 `None` 을 반환한다(200 인데 세 섹션이 다 빈 경우도 실패로 본다), ② `require_sections` 가드가 `None` 뿐 아니라 "모든 섹션이 빈 dict" 도 502 로 막는다. 여기에 `rereview`·`github_push` 가 저장된 `problem_statement` 를 `description` 으로 넘겨 스크래핑 자체를 건너뛴다. `tests/test_push_review_bundle_sections.py` 가 두 플랫폼 × 두 실패 표현을 고정 |
| 재업로드 '제출 일자' | `db.save_review` 는 `timestamps.utc_now_iso()` 로 오프셋 있는 UTC 를 저장한다. 오프셋 없이 저장된 옛 행이 남아 있어, 읽는 쪽이 그 값을 어떤 시간대로 볼지 규칙을 정해야 한다 | `_format_kst` 가 naive 값을 UTC 로 간주해 KST 로 변환한다. `tests/test_helpers_readme.py` 가 naive·UTC·KST 세 입력을 고정 |
| 언어 ↔ 확장자 | `get_file_extension` 이 만든 확장자를 `_ext_to_language` 가 모르면 그 언어로 push 한 풀이를 다시 가져올 때 `language` 가 빈 문자열이 되고, `rereview` 가 파일명을 재현할 수 없다며 재업로드를 거부한다. BOJ 는 `C99`, CF 는 `GNU G++17 7.3.0` 처럼 `c`/`c++` 부분문자열이 없는 표기를 쓴다 | 두 함수를 왕복으로 고정한다 — `tests/test_clients_utils.py` 가 실제 표기 30여 종과 "만들 수 있는 확장자 전체가 역매핑에 있다" 를 검사 |
| GitHub 트리 조회 | 항목 10 만 개 / 7MB 를 넘기면 GitHub 가 `truncated=true` 와 함께 트리를 자른다. 부분 결과를 성공으로 취급하면 가져오기·백필이 **조용히 일부 문제를 누락**한다 | `fetch_repo_tree()` 가 `truncated` 를 확인해 예외로 드러낸다 |
| 성장 곡선 dedupe | `get_tier_history` 는 문제당 **모든 회차**를 준다. 문제당 한 점만 쓰려고 마지막 회차를 남기면, `tier` 는 회차가 아니라 문제의 속성이라 값은 그대로이고 **그 문제가 시계열에 놓이는 날짜만 이동**한다 → 오래된 문제를 재제출하면 이미 지나간 구간의 레이팅이 소급 변한다 | 정순 1패스로 **첫 등장**을 남긴다(서버가 오름차순이므로 재정렬도 불필요). `tests/test_frontend_invariants.py` 가 `.reverse()` 부재를 고정 |
| 뷰어 캐시 vs 붙여넣은 본문 | `closeProblemModal` 이 `_currentProblem` 을 지우지 않으므로, 뷰어를 닫은 뒤 같은 문제를 손으로 입력하면 옛 번역본이 남아 있다. 서버 `resolve_statement` 는 붙여넣은 본문을 우선하는데 프론트가 반대로 고르면 **LLM 리뷰와 GitHub README 의 문제 설명이 갈린다** | `description: pastedStatement \|\| cfSections?.statement` — 서버와 같은 우선순위. 뷰어에서 바로 넘어온 경우엔 `fillReviewForm` 이 textarea 를 비우므로 번역본이 그대로 쓰인다 |
| 목록 데이터 vs DOM | `/api/review-imported` 는 서버에서 `solved_history` 행을 **실제로 삭제**한다. 프론트가 DOM 만 지우면 목록 배열이 stale 이 되고, 필터를 한 번만 만져도 삭제된 항목이 되살아난다(재클릭 시 404) | `requestImportedReview` 를 `loadImportedHistory` 클로저 안에 두어 `allProblems` 에서도 뺀 뒤 재렌더한다 |
| 예제 실행 버튼 | 실행 중(케이스당 최대 5초) 모달을 닫거나 다른 문제를 열면 결과 노드가 사라진다. 노드 확인 없이 쓰면 TypeError 가 나고, **catch 안에서 같은 노드를 다시 참조하면 예외가 함수를 탈출**해 버튼 복원에 도달하지 못한다(새로고침 외 복구 불가) | 세대 토큰으로 갈린 실행을 멈추고, `finally` 로 버튼을 되돌린다. 모달 열기·닫기도 `resetRunButton()` 을 부른다 |
| 서드파티 CDN | `marked`·`DOMPurify` 를 무가드로 부르면 CDN 이 막힐 때 ReferenceError 가 나고, **서버가 이미 저장·과금한 리뷰 결과가 화면에서 통째로 사라진다** | `renderMarkdown()` 한 곳만 두고 미로드 시 평문으로 폴백한다. `Chart`·KaTeX 도 같은 가드를 쓴다 |
| 503 vs 빈 데이터 | `res.ok` 를 보지 않으면 온디맨드 DB 정지(503)가 빈 배열로 흘러 "기록이 없습니다"로 표시된다 — 사용자가 장애를 알 수 없다 | 모든 조회가 `fetchJsonOk` 를 쓴다(비-JSON 응답도 본문 앞머리를 보여준다). `dataset.loaded` 는 성공했을 때만 세운다 |
| CodeMirror 모드 등록 | `mode/rust` 는 `CodeMirror.defineSimpleMode` 를 쓴다 — `addon/mode/simple` 이 없으면 rust.min.js 가 죽고 Rust 하이라이팅이 **조용히 등록되지 않는다**(페이지에 uncaught TypeError 가 남는다) | addon 을 모드 스크립트보다 먼저 로드한다. 모드 등록 여부는 헤드리스 브라우저로 실측해야 잡힌다 |
| CSS 특이도 | 앱 스타일을 서드파티 뒤에 두는 것은 **동일 특이도일 때만** 이긴다. `input[type="text"]`(0,1,1)는 `.cmdk-input`(0,1,0)을 파일 순서와 무관하게 이겨, 그 블록의 선언 6개가 전부 무효였다(테두리 없는 입력이 1px 테두리 + 6px radius + 12px 패딩으로 렌더) | JS 가 만드는 컨트롤에 클래스만 주는 규칙은 요소 선택자를 함께 붙여 특이도를 맞춘다. 헤드리스 브라우저의 computed style 로만 잡힌다 |
| outline 클리핑 | 래퍼에 `overflow:hidden` 이 있으면 **자식**의 `outline-offset` 링은 전량 잘린다 — 포커스 표시가 사라진 채 규칙은 남아 있다 | 링은 래퍼 자신의 `:focus-within` 에 그린다. 자기 overflow 는 자기 outline 을 자르지 않는다 |
| 비텍스트 대비 | 텍스트 대비(1.4.3)만 검산하면 **1.4.11(비텍스트 3:1)** 이 빠진다. 폼·`.btn-secondary`·칩은 배경이 지면과 1.03~1.06:1 이라 테두리가 유일한 식별 수단인데 `--line`/`--line-strong` 은 1.15~1.68:1 이었다 | 컨트롤 경계 전용 `--line-control` 을 분리한다(카드 구분선은 장식이라 대상 아님 — 일괄 상향하면 화면이 시끄러워진다) |
| ARIA 선언 vs 동작 | `role="tablist"` 를 선언하면 보조기술 사용자는 화살표 키 이동을 기대한다. 선언만 있고 동작이 없으면 없는 것보다 나쁘다 | 화살표·Home·End + roving tabindex 를 `tabs.js` 에 둔다. 마크업의 초기 `tabindex` 도 맞춘다(JS 실행 전 상태) |
| 모달 위치 | 탭 섹션 안에 있는 모달은 다른 탭 활성 시 조상이 `display:none` 이 되어 **열 수도, 포커스할 수도 없다** | 모달 셋 전부 body 직하위. Esc·포커스 트랩·초기 포커스·복원은 `modal-a11y.js` 한 곳에서 등록한다(모달마다 복제하면 새 모달에서 또 빠진다) |
| 에디터 안의 Esc | CodeMirror 의 Esc(포커스 탈출)는 기본 동작만 막고 keydown 을 위로 흘려보낸다 — 모달 루트가 그것으로 닫히면 **작성 중이던 코드가 그대로 사라진다**(모달의 에디터 값은 닫는 순간 어디에도 남지 않는다) | 문제 뷰어만 `escapeCloses: false` 로 등록한다(닫기는 ✕ 버튼·바깥 클릭). 에디터가 없는 모달은 그대로 Esc 로 닫힌다 |
| 임시 저장 바인딩 순서 | 문제 뷰어는 열 때 에디터를 비운다. 임시 저장에 **먼저** 붙이면 그 비우기가 변경으로 잡혀 복원본이 빈 값으로 덮인다 | `setEditorValue('pm-code', '')` **뒤에** `bindDraft` 한다. 닫을 때는 `unbindDraft` 가 디바운스 대기분을 먼저 넘긴다 |
| 못 읽은 임시 저장본 | 조회가 실패했는데(온디맨드 DB 정지 등) 자동 저장을 켜면 **첫 타이핑이 읽지 못한 저장본을 덮어쓴다** — 실패한 순간이 곧 유실이다 | 조회 성공 시에만 `loaded` 를 세우고, 그때만 자동 저장한다. 실패한 자리는 '임시 저장' 버튼(수동)으로만 쓴다 |
| 문자열 수준 테스트 | 빌드 스텝이 없어 JS/CSS 배선은 문자열 검사가 유일한 방어선이다. 정확 문자열은 공백·인용부호에 깨지고, 느슨한 부분문자열은 `ArrowRightX` 같은 오타를 통과시킨다. **결함을 설명하는 주석에 그 결함의 코드 형태가 적혀 있어** 거짓 빨강도 난다 | 정규식으로 쓰고, 규칙을 찾는 검사는 주석을 제거한 사본을 본다(`tests/test_frontend_invariants.py`) |
| CSS 형제 결합자 | 인접(`+`)은 DOM 구조 기준이라 `display:none` 형제도 인접을 끊는다 — 가져오기 목록은 행마다 코드 패널 div 를 형제로 끼워 넣으므로 그 탭에서만 구분선이 겹친다 | 목록 행에는 일반 형제(`~`)를 쓴다 |
| 오버레이 높이 | 모달 박스에 `max-height` 가 없으면 콘텐츠만큼 자라서 내부 `overflow-y:auto` 와 `overflow:hidden` 이 전부 무효가 되고(`scrollHeight == clientHeight`) 헤더가 화면 밖으로 나간다 | `.pm-box` 에 상한을 두고 자식은 `min-height:0` 만 갖는다. 자식에 상한을 나눠 주면 헤더 높이를 매직넘버로 빼야 한다 |
| role="button" 안의 링크 | 행 전체를 버튼으로 만들면 `keydown` 의 `preventDefault` 가 자식 앵커의 기본 활성화까지 취소한다 — 마우스는 `stopPropagation` 으로 막혀 정상인데 **키보드만 링크가 죽는다**(WCAG 2.1.1) | `makeRowActivatable` 이 click·keydown 양쪽에서 `e.target.closest('a, button')` 을 걸러낸다 |
| 늦은 응답 경쟁 | `/api/problem/cf/{ref}` 는 스크래핑 + 섹션 4개 번역이라 수 초~십수 초다. A 를 열고 닫은 뒤 B 를 열면 A 의 응답이 B 의 제목·본문·samples·sections 를 덮어, 예제 실행이 B 에 A 의 예제를 돌리고 push 가 B 의 ref 와 A 의 sections 를 함께 보낸다 | `await` 직후 `if (_currentProblem?.ref !== ref) return;`. 예제 실행은 같은 목적으로 세대 토큰(`_runToken`)을 쓴다 |
| JS 구문 게이트 | `node --check static/js/*.js` 는 **첫 파일만** 검사한다 — Node 는 스크립트를 하나만 받고 나머지 위치 인자는 `argv` 가 된다 | `scripts/check_js.sh` 가 파일별로 돌린다 |
| 최상위 이름 충돌 | 전역 렉시컬 스코프를 공유하므로 이름이 겹치면 전체 스크립트가 SyntaxError 로 죽는다. ECMA-262 `GlobalDeclarationInstantiation` 기준으로 **`let`/`const`/`class` 끼리도, 그것과 `function`/`var` 의 교차도 SyntaxError** 다 — 합법인 것은 `function`↔`function` 과 `var`↔`var` 뿐이다. 렉시컬끼리만 보면 교차 조합을 전부 놓친다 | `check_js.sh` 가 렉시컬 중복과 렉시컬×function/var 교집합을 모두 보고, 전 파일을 이어 붙여 한 번 더 파싱한다 |
| JS 고아 파일 | 구문 검사는 통과하지만 `index.html` 에 실리지 않는 파일은 조용히 죽은 코드가 된다 — 어떤 게이트도 이를 보지 않았다 | `check_js.sh` 가 파일마다 `js/<name>?v=` 참조를 확인한다 |
| 환경변수 필터 검증 | import 시점 상수로 두면 그 필터를 실효 검증할 수 없다 — 테스트가 센티넬을 심어도 이미 만들어진 dict 에는 반영되지 않아 필터를 통째로 지워도 통과한다 | `safe_env()` 가 호출 시점에 필터한다. 테스트가 실제 센티넬을 심어 5개 키를 각각 검증 |
| 파이썬 테스트는 JS 를 파싱하지 않는다 | 스크립트로 JS 를 편집하다 개행 이스케이프가 실제 개행으로 치환되면 문자열이 끊겨 **그 파일 전체가 SyntaxError** 가 되고, 전역 스코프를 공유하므로 해당 기능이 통째로 사라진다. pytest 는 이걸 못 잡는다 | CI 의 node 게이트(`scripts/check_js.sh`) 또는 헤드리스 브라우저 실측이 유일한 방어선이다. 파이썬으로 JS 렉서를 흉내 내는 검사는 정규식 리터럴에 걸려 거짓 빨강이 난다 — 시도했다가 되돌렸다 |
| 테스트 DB 격리 | `conftest` 가 `os.environ["DB_TYPE"]` 으로 방언을 판정하면 안 된다 — 실제 접속 대상은 `Settings.sqlalchemy_url` 이고 그것은 `.env` 의 `DATABASE_URL` 을 최우선으로 쓴다. 판정과 접속이 갈리면 sqlite 분기(`DB_PATH` 격리)를 타면서 실DB 에 붙고, `test_migrations` 의 `DROP TABLE` 이 그 DB 로 나간다 | 방언을 **해석된 URL** 에서 유도한다. sqlite 분기는 `DATABASE_URL` 을 지우는 게 아니라 **덮어쓴다** — pydantic-settings 우선순위가 init > OS 환경변수 > dotenv 라 `delenv` 는 `.env` 값을 못 누른다. `_assert_disposable_target()` 이 파일명이 정확히 `test.db` 인 임시 파일 / 로컬 CI postgres 가 아니면 즉시 중단한다(`"test" in name` 부분일치는 `contest.db` 를 통과시킨다) |
| 게이트의 개수 보고 | bash 는 `nullglob` 이 꺼져 있어 매치가 없으면 glob 이 리터럴로 남고 루프가 1회 돈다 — 경로가 틀렸는데 "1개 파일 검사 완료" 가 찍혀 개수를 신뢰할 수 없다 | `scripts/check_js.sh` 가 `shopt -s nullglob` 을 켠다. CI 로그의 "20개 파일 검사 완료" 가 실제 검사 수다 |
| 늦은 응답의 정리 코드 | `finally` 에서 무조건 상태를 되돌리면, 무효화된 옛 실행이 **새로 진행 중인** 실행의 상태를 되살린다(예제 실행 버튼이 활성으로 바뀌고, 다시 누르면 진행 중인 결과가 지워진다) | 세대 토큰을 확인한 뒤에만 되돌린다. 열기·닫기 경로가 이미 복원을 부르므로 "고착 방지" 는 유지된다 |
| 스냅샷 시점 | 테스트가 보는 값이 검증 대상 코드보다 **앞** 시점의 스냅샷이면 그 코드를 지워도 통과한다(`analyze_code` 호출 시점 dict 를 보면 그 뒤의 가드를 검증하지 못한다) | 응답 본문이나 DB 재조회로 확인한다 |
| 필터를 겨냥한 픽스처 | 여러 필터가 순차로 걸리는 함수에서, 픽스처가 **앞선 필터**에 먼저 걸리면 뒤 필터를 지워도 결과가 같다(`4A. Watermelon` 은 루트 필터가 아니라 번호 경계에 걸렸다) | 각 필터마다 그 필터**만**이 이유가 되는 입력을 둔다 |
| 문자 수 윈도우 정규식 | `[\s\S]{0,1200}` 로 함수 안을 찾으면 한두 줄만 추가돼도 "호출이 사라졌다" 는 틀린 메시지로 빨강이 난다(실측 여유 41자·137자) | 중괄호 균형으로 함수 본문을 잘라내고 그 안에서 찾는다(`_js_function_body`) |
| 예외 메시지의 쿼리스트링 | Codeforces 서명 호출은 `apiKey`·`apiSig` 를 **쿼리스트링**에 넣는다. requests 계열 예외 메시지는 요청 URL 전문을 포함하므로, `raise_for_status()` 뿐 아니라 **`requests.get` 자체가 던지는** `ConnectTimeout`/`ConnectionError` 도 키를 싣는다(urllib3 `MaxRetryError` 를 감싼다). 그 예외가 `detail=f"...{e}"` 를 타면 인증 없는 공개 엔드포인트가 운영자 키를 익명 요청자에게 돌려준다 | `_codeforces_api_request` 가 **함수를 나가는 모든 예외**를 원문 없는 `ValueError` 로 치환하고, 라우터는 500 detail 에 타입명만 싣는다. `tests/test_codeforces_credentials.py` 가 전송 예외 4종을 고정 |
| `json.dumps(None)` | 문자열 필드의 `None` 은 NOT NULL 컬럼에서 `IntegrityError` 로 **요란하게** 죽지만, 리스트 필드는 `json.dumps(None)` → `"null"` 이 되어 예외 없이 통과하고 읽을 때 `json.loads` → `None` 이 되어 API 가 `"strengths": null` 을 내보낸다 | 정규화를 생산자(`normalize_review_result`) 한 곳에서 끝내고 문자열·리스트를 함께 다룬다. 저장 함수 둘은 dict 를 직접 받는 공개 경로라 각자 한 번 더 막는다 |
| JSON 모드가 보장하지 않는 것 | `response_format={"type":"json_object"}` 는 Gemini 호환 엔드포인트에서 **문자열 값 안의 이스케이프까지 강제하지 않는다**. 모델이 복잡도를 LaTeX 로 적으면 `$O(N \log N)$` 이 그대로 실려 `\l` 에서 `Invalid \escape` 가 난다. `finish_reason` 은 `stop` 이라 토큰 초과 가드에도 걸리지 않고, 모델이 LaTeX 를 쓸 때만 터지므로 **간헐적**이다(동일 프롬프트 20회 중 5회) | `parse_review_json` 이 파싱 실패 시 이스케이프되지 않은 백슬래시만 이중화해 재파싱한다 — 유효한 이스케이프를 먼저 소비하지 않으면 `C:\\Users` 의 정상 백슬래시까지 망가진다. 프롬프트로도 수식을 일반 텍스트로 요구한다(피드백은 KaTeX 렌더 대상이 아니다) |
| 검색 실패 vs 빈 결과 | 외부 검색이 전면 실패했는데 빈 목록을 돌려주면 호출부가 "조건에 맞는 문제 없음" 과 구분할 수 없다 — 같은 응답에 평균 티어와 취약 태그가 채워져 있어도 UI 는 사용자의 기록이 부족한 것으로 안내한다 | 검색기가 `ProblemSearchError` 를 던지고, 라우터가 `themes` 응답이 이미 쓰던 `error` 필드 계약으로 내려보낸다. 프론트는 `error` 가 있으면 그 이유를 보인다 |
| 마이그레이션 실패 은닉 | "온디맨드 DB 정지 때도 기동은 계속한다" 는 의도로 `except Exception` 을 쓰면 잘못된 리비전·DDL 오류·다중 인스턴스 `upgrade head` 경합까지 warning 한 줄로 덮는다. 새 컬럼이 없는 스키마로 서비스하다 나중에 원인 불명 500 이 난다 | `except OperationalError` 로 좁힌다 — **연결 실패만** 흘려보낸다 |
| 데이터 공백으로 분기 | "BOJ 태그 통계가 비면 CF" 같은 추론은 두 플랫폼을 함께 쓰는 사용자에게서 무너진다 — BOJ 기록이 하나라도 있으면 CF 리포트를 볼 수 없다 | `stats` 와 같이 **명시 쿼리 파라미터**로 받는다. 형제 API 가 파라미터를 쓰는데 하나만 추론하고 있으면 그 자체가 신호다 |
| 같은 제약, 다른 엔드포인트 | 빈 `language` 는 확장자를 `.txt` 로 만들어 rereview 가 **영구 거부**하는 파일을 저장소에 남긴다. 사용자가 폼에서 언어를 고르는 세 엔드포인트가 같은 하류 제약을 공유한다 | 규칙을 `require_language()` 한 곳에 두고 셋이 호출한다. `/api/review-imported` 는 부르지 않는다 — 그 경로의 language 는 가져오기 원본에서 오므로 요청자가 고칠 수단이 없고, 400 으로 막으면 리뷰 자체가 불가능해진다. `require_platform()` 도 같은 이유로 한 곳에 둔다 |
| 비정규화 캐시의 부분 상태 | `tag_stats` 는 `reviews` 의 파생 캐시인데 증분 갱신(`_bump_tag_stats`)이 리뷰 저장 경로만 지나간다 — 백필·마이그레이션·직접 INSERT 로 들어온 행은 반영되지 않는다. "비어 있을 때만 복원" 은 그 부분 상태를 벗어나지 못한다: 백필 500건 + 빈 표에서 새 리뷰 1건이 들어오면 표가 그 1건짜리로 굳고, 비어 있지 않으므로 다시는 복원되지 않는다 | 쿨다운(60초)을 두고 **전면 재계산**한다(`_reconcile_tag_stats`). 다만 재계산을 트리거하는 것은 `get_tag_stats()` 뿐이라 그 캐시를 읽는 소비자에게만 "신선도 문제" 다 — 그 경로를 부르지 않는 소비자(추천)는 캐시를 읽지 않고 `reviews` 에서 직접 센다 |
| 플랫폼별 폴백의 모집단 | 한 플랫폼 전용 집계 함수를 다른 플랫폼의 폴백에 그대로 쓰면, 태그 이름이 겹치는 순간 판정이 새어 든다(BOJ 의 poor 가 CF 추천 점수로). 이름이 겹치지 않는 대부분의 태그에서는 값이 0 이라 **아무도 이상함을 못 느낀다** | 모집단 함수는 플랫폼을 **인자로 받고 기본값을 두지 않는다**. 폴백은 그 플랫폼의 통계 화면과 같은 모집단을 센다(BOJ=문제당 첫 판정 행, CF=전 회차) |
| URL 에 넣는 외부 문자열 | 문제 제목이 그대로 저장소 폴더명이 된다. `?` 는 쿼리 구분자, `#` 는 프래그먼트 구분자라 인코딩 없이 보간하면 요청이 **잘린 경로**로 나간다 — README 와 코드가 같은 경로를 덮어쓰는데 GitHub 는 양쪽 다 2xx 를 주므로 성공으로 집계된다 | 경로를 `quote(path, safe="/")` 로 인코딩한다. 세 함수(`get_github_file_sha`·`push_file_to_github`·`get_raw_github_content`)가 같은 헬퍼를 쓴다 |
| 상태코드 vs 응답 본문 | 상류가 친절한 메시지(`comment`)를 실어 준다고 그것을 먼저 보면, 레이트리밋·점검 응답(5xx·429)이 400(입력 오류)으로 보고된다. 사용자는 자기 입력을 고치려 하고 상류 장애는 알림에 잡히지 않는다 | **상태코드를 먼저** 본다. 4xx 안에서만 `comment` 를 요청자 메시지로 쓴다 |
| 만료 없는 캐시의 추측값 | 추측 키를 만료 없는 성공 캐시에 넣으면 프로세스 수명 동안 남는다. 그 키로 검색하면 200 + 빈 목록이라 예외도 나지 않아 추천이 error 없이 조용히 빈다 | 추측은 **만료를 달아** 별도 dict 에 둔다. "조회 실패"(짧게)와 "조회 성공 + 목록에 없음"(길게)은 성격이 달라 TTL 도 나눈다 |
| 게이트 자신의 사각지대 | 정적 검사가 한 파일을 통째로 못 보게 되어도 **아무것도 빨강이 나지 않는다**(`_is_iife_module` 이 `re.M` 으로 파일 중간의 IIFE 에 걸려 `github.js` 를 깊이 1 기준으로 읽던 때가 그랬다) | 파일마다 마커를 주입해 게이트가 그것을 보는지 확인한다(`test_the_load_order_check_can_see_into_every_file`). 커버리지는 검사 대상 개수의 하한으로도 함께 못박는다 |
| 파생 캐시의 트리거 소유자 | 비정규화 캐시를 최신으로 만드는 코드가 **한 소비자에게만** 붙어 있으면, 그 경로를 부르지 않는 소비자는 낡은 값을 인스턴스 수명 내내 읽는다(`/api/stats` 만 재계산을 트리거하는데 `/api/recommend` 도 같은 표를 읽던 상태) | 캐시를 읽는 소비자는 재계산도 함께 트리거하거나, **아예 원본에서 센다**. 추천은 후자를 택한다 — 이미 같은 행을 읽어 왔으므로 추가 쿼리도 없다 |
| 프로세스 전역 쿨다운 | check 와 set 사이가 보호되지 않으면 콜드 스타트의 동시 요청 N 개가 전부 전면 스캔 + 전면 재기록을 한다. 그 재기록이 증분 갱신의 read-modify-write 와 겹치면 정답이 stale+1 로 덮인다 | `threading.Lock` 으로 감싼다. 표가 **차 있으면** `acquire(blocking=False)` 로 잡고 못 잡으면 기다리지 않는다(최대 `_TAG_STATS_RECONCILE_SEC` 만큼 뒤처진 값을 돌려준다). 표가 **비어 있으면** 최대 `_TAG_STATS_LOCK_WAIT_SEC`(5초) 기다린다 — 그 상태로 응답하면 `/api/report` 가 400 "아직 저장된 기록이 없습니다" 를 낸다. 전면 재기록은 `ORDER BY` 로 잠금 순서를 고정한다 |
| 문자 스트림 파서의 문맥 | 템플릿 리터럴의 `${}` 안을 줄 내용에서 빼면, 그 안의 `/` 앞이 빈 문자열로 보여 나눗셈이 정규식으로 오독된다. 그러면 정규식 본문의 중괄호가 깊이에 섞여 **정상 JS 가 "리터럴 처리가 깨졌다" 는 무관한 메시지로 빨강**이 된다 | 줄 내용용 버퍼와 **정규식 판별용 문맥**을 따로 둔다. 문맥은 `${}` 안도 담고 줄을 넘어 이어진다. `${` 자체는 식의 시작이므로 문맥에 남긴다 |
| 로드 시점 실행의 범위 | 최상위 `if (x) { f(); }` 의 `f()` 는 깊이가 1 이지만 **로드 시점에 실행된다**. 깊이만으로 걸러내면 진짜 로드 순서 위반이 통과한다 | 중괄호마다 그것을 연 것이 제어 블록인지 함수·객체·클래스인지 기록하고, 제어 블록만 거쳐 온 줄은 최상위로 본다 |
| 매직 문자열 계약 | 생산자가 실패를 문자열로 표현하고 소비자가 접두사로 판별하면, 양쪽을 각각 리터럴로 검사하는 테스트는 **문구가 갈려도 전부 초록**이다 | `requests` 만 스텁하고 **실제 생산자**를 호출해 판별자에 넣는다. 정상 본문을 실패로 보지 않는 반대 방향도 함께 고정한다 |
| 실패 폴백이 캐시가 된다 | 조회 실패 시의 자리표시 값을 저장하면, 그 행이 곧 다음 조회의 캐시가 되어 상류가 복구돼도 다시 조회하지 않는다. 파급은 그 리뷰 1건이 아니다 — 집계 기준인 "첫 판정 행" 이 자리표시로 남아 태그 통계·평균 티어·추천이 그 문제를 통째로 빠뜨리고, 삭제·재조회 라우트가 없어 사용자가 복구할 수 없다 | 자리표시를 **알아볼 수 있게** 만들고(제목 형식) 캐시로 인정하지 않는다. 복구되면 과거 행의 메타까지 되살린다 — 제목·티어·태그는 제출이 아니라 문제의 속성이라 갱신이 맞다 |
| 표시값과 기본값 | 추천 난이도의 기본값(평균 티어 10.0)을 그대로 화면에 쓰면 기록이 하나도 없는 사용자에게 "Silver I" 가 뜬다 | 기본값을 주는 함수와 "그 값이 실측인가" 를 알려주는 함수를 나눈다(`has_graded_tier`). 밴드 설명(`tier_range`)은 실제 적용된 파라미터라 감추지 않는다 |
| 세대 토큰의 범위 | "모달이 열려 있는가" 만 보는 가드는 **그 사이 다른 문제를 연 경우**를 막지 못한다 — 늦은 응답이 다른 문제의 화면을 덮는다 | 시작 시점의 세대를 잡아 `await` 뒤에 비교한다. 목록 로더의 클로저도 같다 — 늦게 끝난 호출이 자기 스냅샷을 다시 그리면 새로 불러온 목록이 되돌아간다 |
| 진행 중 상태의 소유자 | 진행 중을 버튼 노드에만 두면 검색·정렬·페이지 이동이 목록을 innerHTML 로 교체할 때 사라진다 — 유료 호출이 두 번 나간다 | 진행 중인 키를 모듈 스코프 집합에 두고, 렌더가 그 집합을 보고 그린다 |
| flex 자동 최소 크기 | `overflow: hidden` 인 flex 자식은 자동 최소 크기가 0 이라 안쪽 `min-height` 아래로 무한 축소되고, 그 차이를 잘라낸다 | 래퍼에도 같은 `min-height` 를 준다. `flex-wrap` 이 없는 헤더도 같은 계열이다 — 좁은 화면에서 닫기 버튼이 화면 밖으로 나간다 |
| 폴더명이 되는 외부 문자열 | 제목의 `/` 는 저장소 폴더 깊이를 한 단계 늘려, 4세그먼트 규약으로 트리를 읽는 재가져오기 파서가 그 문제를 조용히 빠뜨린다 | 경로 **구분자**만 치환한다(`safe_path_segment`). `?` `#` 등은 URL 인코딩이 처리하므로 폴더명을 바꾸지 않는다 — 바꾸면 이미 올라간 폴더와 어긋난다 |
| 로컬에서 건너뛰는 게이트 | `check_js.sh` 의 구문 검사는 node 가 없으면 건너뛴다. 편집 스크립트가 개행 이스케이프를 실제 개행으로 바꾸면 그 파일 전체가 SyntaxError 인데 로컬 게이트가 전부 초록이다 | 같은 사고를 파이썬에서도 잡는다 — 줄을 넘는 따옴표 문자열을 검사한다(`test_no_unterminated_string_literals`) |
| 브랜치 재추측 | GET 으로 main→master 폴백을 해서 기본 브랜치를 알아낸 뒤 PATCH 에서 다시 main 부터 추측하면, master 저장소에서 실패 PATCH 를 낭비하고 폴백 조건(422)에 없는 응답(404)이 오면 **tree·commit 을 이미 만든 상태에서** 예외가 난다 | 알아낸 브랜치를 변수로 잡아 끝까지 쓴다. `tests/test_github_push_branch.py` 가 두 저장소 형태를 고정 |
| 차트 재진입 | `destroy()` 후 `await` 를 거쳐 `new Chart` 를 하면, 겹친 두 호출이 **둘 다** 진입 시점에 인스턴스를 `null` 로 보고 destroy 를 건너뛴다. 뒤늦은 `new Chart` 가 `Canvas is already in use` 를 던지고, 그 예외를 catch 가 안내문 자리에 그대로 표시해 **Chart.js 영문 메시지가 사용자 화면에 뜬다** | 세대 토큰을 둔다. 테마 토글은 재조회 대신 색만 갱신한다(`recolorTierChart`) |
| 마지막 응답이 이긴다 | 목록·토글에서 요청을 연달아 보내면 늦게 온 이전 응답이 새 화면을 덮는다. 칩은 B 가 활성인데 제목은 A 인 상태가 된다 | `problem-modal.js` 의 세대 토큰 규약을 `themes`·`stats`·`history`·`report` 에 같이 적용한다. `setLoading` 이 버튼을 `disabled` 로 만들면 **프로그래매틱 `click()` 은 명세상 이벤트를 발생시키지 않으므로**(재요청이 조용히 무시된다) 핸들러 함수를 직접 부른다 |
| 판정 토큰의 JS 소비 | `--eff-*` 사용처를 CSS 만 훑어 검사하면 절반을 못 본다 — 통계 바와 티어 차트 색은 JS 가 `getComputedStyle` 로 읽는다 | 데이터 시각화용 `--bar-*`/`--chart-line` 을 `--eff-*` 별칭으로 분리하고(초기값 동일이라 화면 무변경), 불변식 테스트가 CSS 와 JS 를 **둘 다** 훑는다 |
| 상속되는 font-weight | `.mono` 가 weight 를 지정하지 않으면 부모(`.summary-value` = 600)를 상속한다. 웹폰트는 400/500 만 로드하므로 브라우저가 **합성 볼드**를 그린다. 규칙 블록 단위로 검사하는 테스트는 두 선언이 다른 블록에 있으면 못 잡는다 | `.mono` 에 weight 를 못박는다. 상속으로 결합되는 문제는 블록 단위 정적 검사의 구조적 한계이므로 computed style 실측이 필요하다 |
| 예외 원문의 응답 노출 | openai SDK 의 `APIStatusError` 메시지는 `Error code: 401 - {제공자 응답 본문}` 형태로 **제공자 본문을 그대로** 싣는다(실측). `.env.example` 이 호환 서드파티 엔드포인트를 1급 대안으로 안내하므로 본문 형태를 통제할 수 없다(제공자가 본문에 자기 주소를 실으면 그것도 함께 나간다) | 라우터는 `upstream_failure()` 로 타입명만 노출하고 세부는 로그로 보낸다. LLM 이 직접 만든 사용자용 안내(`ValueError`)는 그대로 통과시킨다 |
| 상류 장애의 상태코드 | 연결 실패를 입력 오류와 같은 예외 타입으로 치환하면 라우터가 400 으로 매핑한다 — 사용자는 "연결 실패 (ConnectTimeout)" 를 400 과 함께 보고 **자기 입력을 고치려 한다** | `UpstreamUnavailable` 을 따로 두고 502 로 매핑한다. `ValueError` 상속이라 기존 `except ValueError` 는 그대로 동작한다 |
| 캐시 비우고 다시 받기 | `lru_cache.cache_clear()` 는 **먼저 버리고 나중에 받는다**. 재다운로드가 실패하면 정상 스냅샷까지 잃고, 그 뒤 그 기능 전부가 요청마다 재시도한다. `lru_cache` 는 사용자 함수 실행 중 락을 잡지 않아 **동시 miss 를 합치지도 못한다** | 새로 받아 **성공했을 때만 교체**하고, 갱신 구간을 락으로 감싼다(`_try_refresh_snapshot`) |
| 부분 실패 정책 | 같은 예외에 소비처마다 정책이 반대면 한쪽이 틀린 것이다 — 테마는 밴드별로 부분 성공을 살리는데 추천은 첫 실패에서 던져 이미 성공한 태그의 결과까지 버렸다 | 태그별로 격리하고 **전부 실패했을 때만** 실패로 본다 |
| 포커스가 body 로 이탈 | 포커스를 가진 요소가 disabled 되거나(`setLoading`) DOM 에서 사라지면 브라우저가 포커스를 `<body>` 로 옮긴다. keydown 리스너가 모달 root 에 걸려 있으므로 그 순간 **Esc 로 닫을 수 없고 Tab 트랩도 무효**가 된다(10~20초짜리 작업에서 실제로 발생) | `modal-a11y` 가 `focusout` 으로 이탈을 되돌린다. root 에 `tabIndex = -1` 이 필요하다 — 없으면 마지막 수단인 `root.focus()` 가 **조용히 무효**다(안의 버튼이 전부 disabled 면 실제로 그 상황이 된다) |
| 테스트 픽스처의 범위 | "전 파일" 이라 적어 놓고 목록을 고정하면, 그 밖의 파일에는 무엇을 넣어도 통과한다 | glob 으로 읽고 **개수 하한**을 함께 둔다(경로가 틀리면 빈 dict 로 모든 루프가 조용히 통과한다) |
| 전역 스코프 합본 파싱 | 파일별 `node --check` 는 **파일 안**의 구문만 본다. 브라우저는 20개 파일을 하나의 전역 렉시컬 환경에서 평가하므로 `var x` × `const x`, `const a = 1, b = 2` 같은 교차 충돌은 파일별 검사로 볼 수 없다(grep 게이트도 첫 선언자만 본다) | 전부 이어 붙여 한 번 더 `node --check` 한다 — 실행 조건과 같아져 사양대로 잡힌다. 이어 붙여서 새로 생기는 오류는 없다(`function`끼리·`var`끼리 재선언은 합법). CDP `Runtime.compileScript` 로 사양을 실측 검증했고, 합본 파일은 반드시 `.js` 로 만든다 — Node 22 는 확장자로 모듈 타입을 판정해 `mktemp` 의 무확장자 파일에 `ERR_UNKNOWN_FILE_EXTENSION` 을 던진다(게이트 자체가 실패한다) |

---

## 환경변수
전체 목록은 [README](./README.md#환경변수-전체-목록), 값 템플릿과 제공자별 설정 예시는 `.env.example` 참조.
