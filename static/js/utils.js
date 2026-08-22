const TIER_GROUPS = {
  bronze: [1, 5], silver: [6, 10], gold: [11, 15],
  platinum: [16, 20], diamond: [21, 25], ruby: [26, 30], unrated: [0, 0],
};

// 라벨은 배지에 찍히는 티어 이름(Bronze V ...)과 같은 표기를 쓴다 — 필터가 걸러내는
// 대상과 같은 말이어야 한다.
const TIER_GROUP_LABELS = {
  bronze: 'Bronze', silver: 'Silver', gold: 'Gold',
  platinum: 'Platinum', diamond: 'Diamond', ruby: 'Ruby', unrated: 'Unrated',
};

/** 난이도 필터 <option> 목록. 리뷰 기록 탭과 가져온 기록 탭이 같은 목록을 쓴다 —
 *  두 벌로 두면 한쪽에만 그룹이 추가돼 같은 필터가 다르게 동작한다. */
function tierFilterOptionsHtml() {
  // 라벨에 적용 범위를 밝힌다 — 난이도 그룹은 BOJ 티어 체계라 CF 행은 어느 그룹에도
  // 속하지 않는다(tierGroupParams 가 platform 을 boj 로 고정한다). 그 사실을 적지 않으면
  // 난이도를 고르는 순간 CF 기록이 통째로 사라지고 이유를 알 수 없다.
  return ['<option value="">전체 난이도</option>']
    .concat(Object.keys(TIER_GROUPS).map(
      key => `<option value="${key}">${TIER_GROUP_LABELS[key]} (백준)</option>`))
    .join('');
}

function tierClass(tier) {
  if (tier === 0) return '';
  if (tier <= 5) return 'tier-bronze';
  if (tier <= 10) return 'tier-silver';
  if (tier <= 15) return 'tier-gold';
  if (tier <= 20) return 'tier-platinum';
  if (tier <= 25) return 'tier-diamond';
  return 'tier-ruby';
}

// CF 레이팅 → 공식 색상 계열 클래스 (newbie ~ grandmaster)
function cfRatingClass(rating) {
  if (!rating || rating < 1200) return 'cf-newbie';
  if (rating < 1400) return 'cf-pupil';
  if (rating < 1600) return 'cf-specialist';
  if (rating < 1900) return 'cf-expert';
  if (rating < 2100) return 'cf-candidate-master';
  if (rating < 2400) return 'cf-master';
  return 'cf-grandmaster';
}

function tierBadgeHtml(cls, name) {
  return `<span class="tier-badge ${cls}">${name}</span>`;
}

// 백엔드 db.PENDING_EFFICIENCY 와 같은 값 — 리뷰 없이 등록한 행의 마커
const EFF_PENDING = 'pending';

function effClass(e) {
  return { good: 'eff-good', ok: 'eff-ok', poor: 'eff-poor', [EFF_PENDING]: 'eff-pending' }[e] || '';
}

function effLabel(e) {
  return { good: '● 효율적', ok: '◐ 보통', poor: '● 비효율적', [EFF_PENDING]: '◌ 리뷰 대기' }[e] || e;
}

function problemLabel(problem) {
  if (problem.platform === 'codeforces') return problem.problem_ref;
  return String(problem.problem_id ?? problem.problem_ref ?? '');
}

/** 페이지 버튼 목록을 그린다. 리뷰 기록 탭과 가져온 기록 탭이 같은 것을 쓴다 —
 *  두 벌로 두면 한쪽만 고쳐졌을 때 같은 목록이 탭마다 다르게 넘어간다.
 *  @param {HTMLElement} pager  버튼을 담을 컨테이너
 *  @param {number} page        현재 페이지(1부터)
 *  @param {number} totalPages  전체 페이지 수
 *  @param {function(number)} onGo  페이지 번호를 받는 이동 콜백 */
function renderPager(pager, page, totalPages, onGo) {
  if (!pager) return;
  if (totalPages <= 1) { pager.innerHTML = ''; return; }

  let html = `<button class="page-btn" ${page === 1 ? 'disabled' : ''} data-page="${page - 1}">‹</button>`;
  let start = Math.max(1, page - 3);
  const end = Math.min(totalPages, start + 6);
  if (end - start < 6) start = Math.max(1, end - 6);

  if (start > 1) html += `<button class="page-btn" data-page="1">1</button>${start > 2 ? '<span class="page-ellipsis">…</span>' : ''}`;
  for (let i = start; i <= end; i++) {
    html += `<button class="page-btn ${i === page ? 'active' : ''}" data-page="${i}">${i}</button>`;
  }
  if (end < totalPages) html += `${end < totalPages - 1 ? '<span class="page-ellipsis">…</span>' : ''}<button class="page-btn" data-page="${totalPages}">${totalPages}</button>`;
  html += `<button class="page-btn" ${page === totalPages ? 'disabled' : ''} data-page="${page + 1}">›</button>`;
  pager.innerHTML = html;

  pager.querySelectorAll('.page-btn:not([disabled])').forEach(btn => {
    btn.addEventListener('click', () => onGo(Number(btn.dataset.page)));
  });
}

/** 입력이 멈춘 뒤 한 번만 실행한다. 필터 입력마다 서버를 치면 글자당 요청이 나간다. */
function debounce(fn, ms = 250) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

/** 난이도 그룹 키를 서버가 이해하는 tier 범위로 푼다.
 *  그룹 경계의 정의는 이 파일 한 곳에만 둔다 — 서버가 같은 표를 또 가지면 두 벌이 갈린다.
 *  그룹 경계는 solved.ac 티어 1~30 체계라 CF 행(tier 가 항상 0)은 어느 그룹에도 속하지
 *  않는다 — platform 을 함께 고정하지 않으면 'Unrated' 선택에 CF 문제가 전량 딸려 온다. */
function tierGroupParams(key) {
  const r = TIER_GROUPS[key];
  if (!r) return {};
  return { tier_min: r[0], tier_max: r[1], platform: 'boj' };
}

/** 객체를 쿼리스트링으로 만든다 — 빈 값은 빼서 서버 기본값을 쓰게 한다. */
function listQuery(params) {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== '' && v !== null && v !== undefined) sp.set(k, String(v));
  });
  return sp.toString();
}

function cfRefToUrl(ref) {
  const m = String(ref || '').replace(/[^0-9A-Za-z]/g, '').match(/^(\d+)([A-Za-z][A-Za-z0-9]*)$/);
  return m ? `https://codeforces.com/problemset/problem/${m[1]}/${m[2].toUpperCase()}` : '';
}

function problemUrl(problem) {
  // href 에 들어가는 값이므로 http(s) 만 통과시킨다. escapeHtml 은 `javascript:` 스킴을
  // 무력화하지 못한다(problem-modal.js 의 수식 이미지 마커도 같은 허용목록을 쓴다).
  if (/^https?:\/\//i.test(problem.problem_url || '')) return problem.problem_url;
  if (problem.platform === 'codeforces') {
    // 파싱이 실패해도 BOJ 로 흘려보내지 않는다 — "CF 문제인데 백준 링크" 는
    // 깨진 링크보다 알아채기 어려운 조용한 오답이다.
    return cfRefToUrl(problem.problem_ref) || 'https://codeforces.com/problemset';
  }
  return `https://boj.kr/${problem.problem_id ?? problem.problem_ref}`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setLoading(btn, loading) {
  btn.disabled = loading;
  if (loading) {
    // 기본 문구를 '분석 중...' 으로 두면 기록 불러오기·추천받기 같은 버튼에도 그게 뜬다.
    btn.innerHTML =
      `<span class="spinner spinner-sm"></span> ${escapeHtml(btn.dataset.loadingLabel || '처리 중...')}`;
  } else {
    // textContent 로 되돌린다 — dataset.label 은 이미 평문이라 innerHTML 로 넣으면
    // escapeHtml → 속성 → 디코드 → 재주입이라는 불필요한 왕복이 생긴다.
    btn.textContent = btn.dataset.label;
  }
}

function showError(container, msg) {
  // 먼저 보이게 한 뒤 내용을 넣는다 — display:none 상태에서 일어난 변경은 접근성
  // 트리에 없어 aria-live 영역이어도 스크린리더가 첫 메시지를 읽지 않는다.
  container.classList.remove('hidden');
  container.innerHTML = `<div class="alert alert-error">${escapeHtml(msg)}</div>`;
}

async function fetchJsonOk(url, options, fallbackMsg) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch (e) {
    // 프록시 오류 페이지·게이트웨이 HTML 처럼 JSON 이 아닌 응답 — 본문 앞머리를 보여주지
    // 않으면 "실패" 한 마디만 남아 원인을 알 수 없다.
    throw new Error(`응답 형식 오류(${res.status}): ${text.slice(0, 100)}`);
  }
  // pydantic 검증 실패(422)는 detail 이 객체 배열이라 그대로 쓰면 "[object Object]" 가 보인다.
  if (!res.ok) throw new Error(errorDetail(data) || fallbackMsg);
  return data;
}

function errorDetail(data) {
  const d = data && data.detail;
  if (Array.isArray(d)) return d.map(e => (e && e.msg) || '').filter(Boolean).join(' / ');
  return typeof d === 'string' ? d : '';
}

/** 마크다운을 안전한 HTML 로 만든다. CDN(marked·DOMPurify)이 막히면 평문으로 폴백한다 —
 *  가드가 없으면 ReferenceError 가 나고, 서버가 이미 저장·과금한 리뷰 결과가
 *  화면에서 통째로 사라진다. Chart·KaTeX 도 같은 가드를 쓴다. */
function renderMarkdown(text) {
  const raw = text || '';
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
    return `<pre class="code-block">${escapeHtml(raw)}</pre>`;
  }
  return DOMPurify.sanitize(marked.parse(raw));
}

/** div 를 버튼처럼 쓰는 곳에 키보드 접근을 준다. role/tabindex 만 붙여도 Enter/Space 가
 *  동작하지 않으므로 키보드 핸들러까지 함께 건다. */
function makeRowActivatable(el, onActivate) {
  el.setAttribute('role', 'button');
  el.setAttribute('tabindex', '0');

  // 행 안의 링크·버튼은 자기 동작을 해야 한다. 이 가드가 없으면 keydown 의
  // preventDefault 가 앵커의 기본 활성화(내비게이션)까지 취소해, 링크에 포커스한 채
  // Enter 를 눌러도 문제 페이지가 열리지 않고 행 모달이 열린다(WCAG 2.1.1 위반).
  const fromChildControl = e => e.target !== el && e.target.closest('a, button');

  el.addEventListener('click', e => {
    if (fromChildControl(e)) return;
    onActivate(e);
  });
  el.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (fromChildControl(e)) return;
    e.preventDefault();
    onActivate(e);
  });
}

// 코드 본문에서 제출 언어를 추론한다. 반환값의 도메인은 #code-language 의 option value
// 와 같다 — 어느 것도 맞지 않으면 '' 를 돌려주고, 호출부가 사용자에게 직접 선택을 요구한다.
//
// 순서가 곧 규칙이다: **좁은 마커를 먼저**, 여러 언어가 공유하는 넓은 마커를 나중에 본다.
// `import`·`print(`·`std::`·`require(` 같은 마커는 여러 언어에 공통이라, 먼저 두면 그
// 마커를 함께 쓰는 다른 언어를 전부 흡수한다.
// 판정 결과는 tests/test_language_detection.py 가 언어별 관용 코드로 고정한다.
const _LANG_PATTERNS = [
  // 1) 한 언어에만 나타나는 선언·호출 형태
  ['Kotlin', /\bfun\s+\w+\s*\(|\breadLine\(\)!!|\bval\s+\w+\s*=/],
  ['Rust', /\bfn\s+main\s*\(|\blet\s+mut\b|\buse\s+std::/],
  ['Go', /\bpackage\s+main\b|\bfmt\.(?:Print|Scan|Sprint|Fprint)/],
  ['C#', /\busing\s+System\b|\bConsole\s*\.\s*(?:Write|Read)/],
  ['Java', /\bpublic\s+class\b|\bSystem\s*\.\s*out\b|\bBufferedReader\b|\bScanner\b|\bimport\s+java\./],
  ['Swift', /\bimport\s+Foundation\b|\breadLine\(\)!(?!!)|\bfunc\s+\w+\s*\([^)]*\)\s*(?:->|\{)/],
  // 2) C 계열 — C++ 고유 마커가 있으면 C++, 없으면 C
  ['GNU C++17', /\bstd::|\bcout\b|\bcin\b|\busing\s+namespace\s+std\b|\bvector\s*<|\bendl\b/],
  ['C', /#include\b|\bprintf\s*\(|\bscanf\s*\(/],
  // 3) Ruby 는 C 뒤에 둔다. `puts(…)`·`gets(…)` 는 C 표준 함수이기도 하므로 여기서는
  //    괄호를 쓰지 않는 Ruby 관용형(`puts x`, `gets.chomp`)과 Ruby 고유 메서드만 본다.
  ['Ruby', /\bputs\s+[^(\s]|\bgets\s*\.|\.to_i\b|\.to_s\b|^\s*(?:def|class|module)\s+\w[\s\S]*?^\s*end\s*$/m],
  // 4) TypeScript 는 JavaScript 의 상위집합이라 타입 표기로만 구분된다
  ['TypeScript', /\binterface\s+\w+\s*\{|:\s*(?:string|number|boolean|void|any)\b|\bas\s+(?:string|number)\b/],
  // 5) 여러 언어가 공유하는 마커
  ['JavaScript', /\bconsole\s*\.\s*log\b|\brequire\s*\(|\bdocument\s*\./],
  ['Python 3', /\bdef\s+\w+\s*\(|\bprint\s*\(|\binput\s*\(|\brange\s*\(|\bimport\s+\w/],
];

function detectLanguage(code) {
  const src = code || '';
  for (const [language, pattern] of _LANG_PATTERNS) {
    if (pattern.test(src)) return language;
  }
  return '';
}
