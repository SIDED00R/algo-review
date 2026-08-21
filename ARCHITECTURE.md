# Architecture

## 레이어 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (static/js/*.js)                                       │
│  editor · utils · theme · github · tier-chart · tabs           │
│  review · recommend · themes · problem-modal · stats            │
│  history · report                                               │
│  import-history · import-github · import-boj · import-codeforces│
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP (fetch)
┌────────────────────────▼────────────────────────────────────────┐
│  FastAPI Routes (routes/)                                       │
│  auth · review · pending_review · rereview · github_push        │
│  problem · execute · recommend · themes · history · solved      │
│  stats · report · import_github · import_boj · import_codeforces│
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
│  normalize                   │
└────────┬────────────────────┘
         │
┌────────▼──────────────────────┐
│  SQLite / PostgreSQL          │   (스키마: Alembic 마이그레이션)
└───────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  warmup.py — server.py lifespan 기동 시 백그라운드 태스크로 실행     │
│  themes.py.get_theme_problem_pool() 를 플랫폼×테마 전수 호출해 예열 │
└───────────────────────────────────────────────────────────────────┘
```

---

## 파일 책임 목록

### 서버 진입점
| 파일 | 단일 책임 |
|------|----------|
| `server.py` | FastAPI 앱 초기화, 미들웨어·라우터 등록, `lifespan`으로 DB 마이그레이션/데모 시드 + 테마 캐시 예열 기동, `GET /health`, 전역 예외 핸들러 |
| `config.py` | 모든 환경변수를 읽는 중앙 설정(pydantic-settings) — DB URL + OpenAI/GitHub/CF/CORS 등 |
| `warmup.py` | 기동 직후 백그라운드로 플랫폼×테마 문제 풀 캐시 예열 |
| `backfill_statements.py` | 기존 기록의 `problem_statement` 백필(일회성 CLI). BOJ 는 GitHub README, CF 는 codeforces.com 재수집. dry-run 기본, `--apply` 로만 기록 |

### 서비스 레이어
| 파일 | 단일 책임 |
|------|----------|
| `analyzer.py` | OpenAI GPT를 이용한 코드 분석 |
| `recommender.py` | 취약 태그 기반 문제 추천 알고리즘 |
| `themes.py` | 테마(알고리즘 분야)별 플랫폼별(CF/백준) 대표 문제 풀 조회, 네이티브 난이도 밴드 분류 + DB 캐시 |
| `cf_translator.py` | OpenAI를 이용한 Codeforces 문제 본문 한국어 번역 |

### 데모 인프라
| 파일 | 단일 책임 |
|------|----------|
| `demo_mode.py` | 데모 모드 플래그(`IS_DEMO`)와 라우터가 반환하는 mock 응답 데이터 |
| `demo_seed.py` | 데모 서버 기동 시 SQLite 샘플 데이터 시딩 |

### DB 레이어 (`db/`)
SQLAlchemy 2.0 ORM 을 쓴다. SQLite(로컬/데모) ↔ PostgreSQL(운영) 은 접속 URL 만 다르고
쿼리 코드는 단일 경로다(수동 방언 분기 없음). 스키마는 Alembic 으로 버전 관리한다.

| 파일 | 단일 책임 |
|------|----------|
| `db/models.py` | ORM 모델 5개(Review·TagStat·SolvedHistory·GithubSetting·ApiCache) + 인덱스. `reviews.problem_statement` 는 불러오기로 폼을 복원할 때 쓰는, 사용자가 붙여 넣은 원문이다 |
| `db/connection.py` | 지연 엔진 싱글턴(`get_engine`)·세션 컨텍스트(`session_scope`)·`dispose_engine` |
| `db/migrate.py` | 프로그래매틱 Alembic `upgrade head` 실행(`run_migrations`) |
| `db/normalize.py` | reviews/solved 행 정규화 공용 헬퍼 (platform·problem_ref·tags·tier_name 폴백) |
| `db/reviews.py` | reviews 테이블 CRUD + 티어/태그 집계 쿼리 + 리뷰 대기 마커(`PENDING_EFFICIENCY`) 처리 |
| `db/solved.py` | solved_history 테이블 CRUD |
| `db/github_settings.py` | github_settings 테이블 CRUD |
| `db/cache.py` | api_cache 테이블 CRUD — 외부 API 파생 페이로드 TTL 캐시 (`cache_get`/`cache_get_stale`/`cache_set`) |
| `db/__init__.py` | 패키지 외부(라우터·서비스)에서 사용하는 함수 re-export |
| `migrations/` | Alembic 환경(`env.py`) + 리비전(`versions/`) |

### 외부 클라이언트 레이어 (`clients/`)
| 파일 | 단일 책임 |
|------|----------|
| `clients/solved_ac.py` | solved.ac API, BOJ 스크래핑, TIER_NAMES 상수 |
| `clients/codeforces.py` | Codeforces API, 문제 메타/본문 스크래핑 |
| `clients/github.py` | GitHub OAuth, 파일 push, BaekjoonHub import, 저장소 트리 조회(`fetch_repo_tree`·`get_boj_readme_paths`) |
| `clients/utils.py` | `get_problem_url()`, 파일 확장자 매핑 |
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
| `routes/execute.py` | `POST /api/execute` | Python/C++ 코드 실행 |
| `routes/recommend.py` | `GET /api/recommend` | 문제 추천 API |
| `routes/themes.py` | `GET /api/themes`, `GET /api/themes/{theme_id}/problems` | 테마 목록 + 플랫폼별 테마 문제 조회 (푼 문제 제외) |
| `routes/history.py` | `GET /api/reviews/grouped`, `GET /api/reviews/problem/{platform}/{ref}` | 리뷰 기록 조회 |
| `routes/solved.py` | `/api/solved-history/*`, `POST /api/review-imported/*` | 가져온 기록 관리 + AI 리뷰 요청 |
| `routes/stats.py` | `GET /api/stats`, `GET /api/tier-history` | 통계 및 티어 이력 조회 |
| `routes/report.py` | `GET /api/report` | 종합 분석 리포트 생성 |
| `routes/import_github.py` | `POST /api/import-github` | BaekjoonHub 저장소 가져오기 |
| `routes/import_boj.py` | `POST /api/import` | BOJ 제출 기록 크롤링 가져오기 |
| `routes/import_codeforces.py` | `POST /api/import-codeforces` | Codeforces 제출 기록 가져오기 |
| `routes/models.py` | — | Pydantic 요청/응답 스키마 |
| `routes/helpers.py` | — | GitHub push 공용 헬퍼 (README 빌더 + 리뷰 섹션, 저장 폴더·커밋 메시지 조립, 설정+override 병합, README+코드 번들 push) |
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
| `import-boj.js` | BOJ 제출 기록 import 버튼 핸들러 |
| `import-codeforces.js` | Codeforces import 버튼 핸들러 |

---

## 주요 호출 관계

| Caller | Callee | 목적 |
|--------|--------|------|
| `server.py` | `db.run_migrations` | lifespan 기동 시 Alembic `upgrade head` |
| `server.py` | `warmup.warm_theme_caches` | lifespan 기동 시 테마 캐시 예열 백그라운드 태스크 시작 (데모 제외) |
| `warmup.py` | `themes.get_theme_problem_pool` | 플랫폼×테마 전수 순회하며 캐시 예열 |
| `routes/problem_resolve.py` | `clients.get_codeforces_problem_info` | CF 문제 메타데이터 조회 |
| `routes/problem_resolve.py` | `clients.get_problem_info` | BOJ 문제 메타데이터 조회 |
| `routes/review.py` | `analyzer.analyze_code` | GPT-4o 코드 분석 |
| `routes/review.py` | `db.save_review` | 리뷰 결과 저장 |
| `routes/pending_review.py` | `db.save_review` | 리뷰 대기 행 저장 (push 성공 후에만) |
| `routes/rereview.py` | `analyzer.analyze_code` | 대기 행 재리뷰 — LLM 을 호출하는 두 번째 경로 |
| `routes/rereview.py` | `db.update_pending_review` | 대기 행을 리뷰 결과로 갱신 + 태그 통계 첫 집계 |
| `routes/helpers.py` | `clients.push_files_to_github` | 코드+README 단일 커밋 GitHub push |
| `routes/problem.py` | `clients.scrape_cf_problem` | CF 문제 본문 스크래핑 |
| `routes/problem.py` | `cf_translator.translate_cf_text` | CF 본문 OpenAI 한국어 번역 |
| `routes/helpers.py` | `clients.tex_markers_to_markdown` | README push 시 수식 이미지 마커 → 마크다운 |
| `routes/execute.py` | `subprocess.run` | 격리된 환경에서 코드 실행 |
| `routes/stats.py` | `db.get_average_tier` | BOJ 평균 티어 계산 |
| `routes/report.py` | `analyzer.get_cumulative_analysis` | GPT-4o 종합 리포트 생성 |
| `routes/import_boj.py` | `clients.get_user_submissions` | BOJ 제출 목록 크롤링 |
| `routes/import_boj.py` | `clients.get_problems_bulk` | 대량 문제 정보 조회 |
| `routes/import_github.py` | `clients.get_baekjoonhub_problems` | BaekjoonHub 저장소 트리 파싱 |
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

---

## 보안 조치 내역

| # | 위치 | 조치 내용 |
|---|------|----------|
| 1 | `routes/execute.py` | subprocess 실행 시 `_SAFE_ENV_KEYS`만 허용 → API 키 환경변수 노출 차단 |
| 2 | `db/` | SQLAlchemy ORM 전환으로 raw SQL f-string 제거 — 쿼리가 전부 파라미터 바인딩되어 SQL injection 표면 소멸 |
| 3 | `routes/auth.py` | OAuth 실패 시 예외 메시지 redirect URL 노출 제거, 서버 로그만 기록 |
| 4 | `server.py` | `CORSMiddleware` 추가 (환경변수 `CORS_ORIGINS`로 허용 출처 설정) |
| 5 | `server.py` | 전역 예외 핸들러 — DB 연결 실패(`OperationalError`)는 503 + 안내, 그 외 미처리 예외는 500 generic(내부 상세 비노출) + traceback 로깅 |
| 6 | `routes/models.py` | `ExecuteRequest` validator: 코드 50,000자, 입력 10,000자, timeout 1~10초 제한 |

---

## 조용한 오답이 나는 지점

테스트가 없으면 잡히지 않고, 실패하지도 않으면서 결과만 틀리는 곳이다.

| 지점 | 내용 | 방어 |
|------|------|------|
| `routes/problem_resolve.py` `resolve_statement` | 요청에 `problem_statement` 가 있으면 **무조건** 그것을 쓴다. 이전 문제의 붙여넣은 본문이 폼에 남아 있으면 다른 문제를 그 본문으로 리뷰한다 | `load-submission.js` 가 값이 없어도 `''` 를 조건 없이 대입한다. `tests/test_load_submission_wiring.py` 가 이 코드의 존재를 고정 |
| `reviews.language` | 자유 문자열이다 — import 경로가 CF/BOJ 원문(`"GNU G++17 7.3.0"`)을 그대로 저장한다. `select.value` 에 없는 값을 넣으면 조용히 실패해 빈 select 가 된다 | `submissionLanguageOption()` 이 option 존재를 확인하고, 없으면 `detectLanguage(code)` 로 재추론한다(반환 도메인이 option value 와 같다) |
| 탭 전환 | 전환 로직을 복제하면 탭별 lazy loader 와 모바일 메뉴 닫기를 건너뛴다 | `activateTab()` 한 곳만 둔다. 배선 테스트가 다른 JS 에 `.tab-content` 토글이 없음을 확인 |
| 본문 수집 함수 | `get_problem_statement()`·`get_codeforces_problem_statement()` 는 예외를 던지지 않고 **실패 문자열**을 반환한다. acmicpc.net 종료 후 BOJ 리뷰는 프롬프트의 문제 설명 자리에 `"크롤링 실패: 404 …"` 를 넣고 있었다 | LLM 에 본문을 넘기는 **세 경로 전부**(`review`·`rereview`·`review-imported`)가 `resolve_statement()` 를 쓴다 — `is_scrape_failure()` 로 걸러 빈 본문을 준다. 백필도 저장 직전에 같은 검사를 한다(저장하면 그 문제의 리뷰가 영구히 오염된다). **수집 함수를 직접 부르는 경로를 새로 만들면 안 된다** — 예전에 `review-imported` 가 그래서 상시 오염 상태였다 |
| BOJ README 경로 |  저장소 폴더명은 BaekjoonHub 규칙이라 공백이 `U+2005`, 특수문자가 전각(`A＋B`)이고 `번` 이 없다. 티어 폴더도 저장 당시 값이라 DB 와 다르다(acmicpc 종료 후 조회 실패로 `Unrated` 인 행이 많다) → 경로를 조립하면 거의 다 404 다 | `get_boj_readme_paths()` 로 트리를 한 번 받아 번호로 찾는다. 번호 경계를 느슨하게 보면 `2024 대회 후기` 를 2024번 문제로 오인한다 |
| BOJ README 재푸시 | 수집 실패를 빈 섹션으로 오인하면 본문 없는 README 로 덮어써 **이미 올라간 문제 설명이 지워진다** | 두 겹으로 막는다 — ① `get_boj_problem_sections()` 가 `get_cf_problem_sections()` 와 같은 계약으로 실패 시 `None` 을 반환한다(200 인데 세 섹션이 다 빈 경우도 실패로 본다), ② `require_sections` 가드가 `None` 뿐 아니라 "모든 섹션이 빈 dict" 도 502 로 막는다. 여기에 `rereview`·`github_push` 가 저장된 `problem_statement` 를 `description` 으로 넘겨 스크래핑 자체를 건너뛴다. `tests/test_push_review_bundle_sections.py` 가 두 플랫폼 × 두 실패 표현을 고정 |
| 재업로드 '제출 일자' | `db.save_review` 는 `datetime.now()` 를 **tz 없이** 저장하고 Cloud Run 컨테이너는 UTC 다. `_format_kst` 가 변환하지 않으면 최초 push(KST)와 재푸시(UTC)의 날짜가 9시간 어긋난다 | `_format_kst` 가 naive 값을 UTC 로 간주해 KST 로 변환한다. `tests/test_helpers_readme.py` 가 naive·UTC·KST 세 입력을 고정 |
| 언어 ↔ 확장자 | `_get_file_extension` 이 만든 확장자를 `_ext_to_language` 가 모르면 그 언어로 push 한 풀이를 다시 가져올 때 `language` 가 빈 문자열이 되고, `rereview` 가 파일명을 재현할 수 없다며 재업로드를 거부한다. BOJ 는 `C99`, CF 는 `GNU G++17 7.3.0` 처럼 `c`/`c++` 부분문자열이 없는 표기를 쓴다 | 두 함수를 왕복으로 고정한다 — `tests/test_clients_utils.py` 가 실제 표기 30여 종과 "만들 수 있는 확장자 전체가 역매핑에 있다" 를 검사 |
| GitHub 트리 조회 | 항목 10 만 개 / 7MB 를 넘기면 GitHub 가 `truncated=true` 와 함께 트리를 자른다. 부분 결과를 성공으로 취급하면 가져오기·백필이 **조용히 일부 문제를 누락**한다 | `fetch_repo_tree()` 가 `truncated` 를 확인해 예외로 드러낸다 |

---

## 환경변수
전체 목록은 [README](./README.md#환경변수-전체-목록), 값 템플릿과 제공자별 설정 예시는 `.env.example` 참조.
