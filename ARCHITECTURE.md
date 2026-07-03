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
│  auth · review · github_push · problem · execute · recommend   │
│  themes · history · solved · stats · report                    │
│  import_github · import_boj · import_codeforces                │
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
│  DB Layer (db/)              │       │  External APIs                   │
│  connection · schema         │       │  solved.ac · Codeforces          │
│  reviews · solved            │       │  GitHub · OpenAI                 │
│  github_settings · cache     │       └──────────────────────────────────┘
└────────┬────────────────────┘
         │
┌────────▼──────────────────────┐
│  SQLite / PostgreSQL          │
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
| `server.py` | FastAPI 앱 초기화, 미들웨어·라우터 등록, `lifespan`으로 DB init/데모 시드 + 테마 캐시 예열 기동 |
| `warmup.py` | 기동 직후 백그라운드로 플랫폼×테마 문제 풀 캐시 예열 |

### 서비스 레이어
| 파일 | 단일 책임 |
|------|----------|
| `analyzer.py` | OpenAI GPT를 이용한 코드 분석 |
| `recommender.py` | 취약 태그 기반 문제 추천 알고리즘 |
| `themes.py` | 테마(알고리즘 분야)별 플랫폼별(CF/백준) 대표 문제 풀 조회, 네이티브 난이도 밴드 분류 + DB 캐시 |
| `cf_translator.py` | OpenAI를 이용한 Codeforces 문제 본문 한국어 번역 |

### DB 레이어 (`db/`)
| 파일 | 단일 책임 |
|------|----------|
| `db/connection.py` | DB 연결 팩토리 (SQLite / PostgreSQL), `db_cursor()` 컨텍스트 매니저, `_ph()`, `_rows_to_dicts()` |
| `db/schema.py` | 테이블 생성 및 마이그레이션 (컬럼 추가) |
| `db/reviews.py` | reviews 테이블 CRUD + 티어/태그 집계 쿼리 |
| `db/solved.py` | solved_history 테이블 CRUD |
| `db/github_settings.py` | github_settings 테이블 CRUD |
| `db/cache.py` | api_cache 테이블 CRUD — 외부 API 파생 페이로드 TTL 캐시 (`cache_get`/`cache_get_stale`/`cache_set`) |
| `db/__init__.py` | 모든 public 함수 re-export (하위 호환) |

### 외부 클라이언트 레이어 (`clients/`)
| 파일 | 단일 책임 |
|------|----------|
| `clients/solved_ac.py` | solved.ac API, BOJ 스크래핑, TIER_NAMES 상수 |
| `clients/codeforces.py` | Codeforces API, 문제 메타/본문 스크래핑 |
| `clients/github.py` | GitHub OAuth, 파일 push, BaekjoonHub import |
| `clients/utils.py` | `get_problem_url()`, 파일 확장자 매핑 |
| `clients/__init__.py` | 모든 public 함수 re-export (하위 호환) |

### API 라우터 (`routes/`)
| 파일 | 엔드포인트 | 단일 책임 |
|------|-----------|----------|
| `routes/auth.py` | `/auth/github/*` | GitHub OAuth 인증 흐름 |
| `routes/review.py` | `POST /api/review` | AI 코드 리뷰 생성 |
| `routes/github_push.py` | `POST /api/push-review` | GitHub 저장소에 코드+README push |
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
| `routes/helpers.py` | — | GitHub README 빌더 + 풀이 파일 push 헬퍼 |
| `routes/review_response.py` | — | 리뷰 저장 + ReviewResponse 생성 (review/solved 공용) |

### 프론트엔드 (`static/js/`)
| 파일 | 단일 책임 |
|------|----------|
| `utils.js` | 공통 순수 함수 (tierClass, cfRatingClass, escapeHtml, detectLanguage 등) |
| `editor.js` | CodeMirror 에디터 초기화 및 관리 |
| `theme.js` | 다크/라이트 테마 토글 |
| `github.js` | GitHub OAuth 연결 UI |
| `tabs.js` | 탭 전환 네비게이션 |
| `review.js` | 코드 리뷰 제출 및 결과 표시 |
| `recommend.js` | 문제 추천 표시 |
| `themes.js` | 테마별 문제 탭 — 플랫폼 토글, 테마 칩, 3계층 캐시(메모리/localStorage/서버), 유휴 프리페치 |
| `problem-modal.js` | CF 문제 모달 (조회, 샘플 실행, 리뷰 이동) |
| `stats.js` | 태그 통계 시각화 |
| `tier-chart.js` | 티어 변화 Chart.js 그래프 |
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
| `server.py` | `db.init_db` | lifespan 기동 시 스키마 마이그레이션 (데모는 `demo_seed.seed` 대신 실행) |
| `server.py` | `warmup.warm_theme_caches` | lifespan 기동 시 테마 캐시 예열 백그라운드 태스크 시작 (데모 제외) |
| `warmup.py` | `themes.get_theme_problem_pool` | 플랫폼×테마 전수 순회하며 캐시 예열 |
| `routes/review.py` | `clients.get_codeforces_problem_info` | CF 문제 메타데이터 조회 |
| `routes/review.py` | `clients.get_problem_info` | BOJ 문제 메타데이터 조회 |
| `routes/review.py` | `analyzer.analyze_code` | GPT-4o 코드 분석 |
| `routes/review.py` | `db.save_review` | 리뷰 결과 저장 |
| `routes/github_push.py` | `clients.push_files_to_github` | 코드+README 단일 커밋 GitHub push |
| `routes/problem.py` | `clients.scrape_cf_problem` | CF 문제 본문 스크래핑 |
| `routes/problem.py` | `cf_translator.translate_cf_text` | CF 본문 OpenAI 한국어 번역 |
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
| `recommend.js` | `GET /api/recommend` | 문제 추천 요청 |
| `themes.js` | `GET /api/themes` | 테마 목록 요청 (localStorage 24h 캐시) |
| `themes.js` | `GET /api/themes/{theme_id}/problems` | 플랫폼별 테마 문제 요청 (메모리/localStorage 30분 캐시) |
| `import-history.js` | `GET /api/solved-history` | 가져온 기록 목록 조회 |

---

## 보안 조치 내역

| # | 위치 | 조치 내용 |
|---|------|----------|
| 1 | `routes/execute.py` | subprocess 실행 시 `_SAFE_ENV_KEYS`만 허용 → API 키 환경변수 노출 차단 |
| 2 | `db/schema.py` | ALTER TABLE f-string에 `_ALLOWED_*_COLS` 화이트리스트 검증 추가 |
| 3 | `routes/auth.py` | OAuth 실패 시 예외 메시지 redirect URL 노출 제거, 서버 로그만 기록 |
| 4 | `server.py` | `CORSMiddleware` 추가 (환경변수 `CORS_ORIGINS`로 허용 출처 설정) |
| 5 | `routes/models.py` | `ExecuteRequest` validator: 코드 50,000자, 입력 10,000자, timeout 1~10초 제한 |

---

## 환경변수 레퍼런스

| 변수 | 필수 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | AI 코드 리뷰·리포트 및 CF 문제 번역 |
| `GITHUB_CLIENT_ID` | — | GitHub OAuth 앱 Client ID |
| `GITHUB_CLIENT_SECRET` | — | GitHub OAuth 앱 Client Secret |
| `APP_URL` | — | 서버 공개 URL (OAuth redirect 용, 예: `https://myapp.run.app`) |
| `CODEFORCES_API_KEY` | — | CF API 서명 (소스코드 가져오기용) |
| `CODEFORCES_API_SECRET` | — | CF API 서명 |
| `OPENAI_MODEL` | — | 사용할 OpenAI 모델 — 미설정 시 리뷰·리포트 `gpt-4o`, 번역 `gpt-4o-mini`. 설정하면 둘 다 이 값으로 대체 |
| `OPENAI_MAX_TOKENS` | — | 리뷰·번역 응답 최대 토큰 (기본값: 리뷰 `2048`, 번역 `2000`) |
| `OPENAI_REPORT_MAX_TOKENS` | — | 종합 리포트 응답 최대 토큰 (기본값: `1024`) |
| `OPENAI_TEMPERATURE` | — | CF 번역 temperature (기본값: `0.3`) |
| `OPENAI_TIMEOUT` | — | CF 번역 API 타임아웃(초) (기본값: `15`) |
| `COMPILE_TIMEOUT` | — | `/api/execute` C++ 컴파일 타임아웃(초) (기본값: `30`) |
| `DB_TYPE` | — | `postgres` 설정 시 PostgreSQL 사용 (기본: SQLite) |
| `DB_PATH` | — | SQLite 파일 경로 (기본값: 프로젝트 루트 `coding_recommend.db`) |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | — | PostgreSQL 연결 정보 |
| `DB_HOST` / `DB_PORT` / `DB_SOCKET` | — | PostgreSQL 호스트 설정 |
| `CORS_ORIGINS` | — | 허용할 CORS 출처 (쉼표 구분, 기본: `http://localhost:8080`) |
| `DEMO_MODE` | — | `true` 설정 시 mock 데이터로 동작 (외부 API 키 불필요) |
