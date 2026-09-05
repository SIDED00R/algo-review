const TIER_GROUPS = {
  bronze: [1, 5], silver: [6, 10], gold: [11, 15],
  platinum: [16, 20], diamond: [21, 25], ruby: [26, 30], unrated: [0, 0],
};

const TIER_GROUP_LABELS = {
  bronze: 'Bronze', silver: 'Silver', gold: 'Gold',
  platinum: 'Platinum', diamond: 'Diamond', ruby: 'Ruby', unrated: 'Unrated',
};

/** 난이도 필터 <option> 목록. 리뷰 기록 탭과 가져온 기록 탭이 함께 쓴다. */
function tierFilterOptionsHtml() {
  // 라벨의 '(백준)' — 난이도 그룹은 BOJ 티어 체계라 CF 행은 어느 그룹에도 속하지 않는다.
  return ['<option value="">전체 난이도</option>']
    .concat(Object.keys(TIER_GROUPS).map(
      key => `<option value="${key}">${TIER_GROUP_LABELS[key]} (백준)</option>`))
    .join('');
}

function tierClass(tier) {
  if (tier === 0) return '';
  // TIER_GROUPS 는 티어 오름차순이다 — 상한을 처음 넘지 않는 그룹이 그 티어의 그룹이다.
  for (const [key, [, hi]] of Object.entries(TIER_GROUPS)) {
    if (key !== 'unrated' && tier <= hi) return `tier-${key}`;
  }
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

/** 페이지 버튼 목록을 그린다. 리뷰 기록 탭과 가져온 기록 탭이 함께 쓴다.
 *  @param {HTMLElement} pager  버튼을 담을 컨테이너
 *  @param {number} page        현재 페이지(1부터)
 *  @param {number} totalPages  전체 페이지 수
 *  @param {function(number)} onGo  페이지 번호를 받는 이동 콜백 */
function renderPager(pager, page, totalPages, onGo) {
  if (!pager) return;
  // innerHTML 교체는 포커스를 <body> 로 떨어뜨린다 — 키보드로 페이지를 넘기던 사용자가
  // 매번 다시 Tab 을 눌러야 한다. 교체 전 포커스가 페이저 안에 있었는지 기록해 둔다.
  const hadFocus = pager.contains(document.activeElement);
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
  if (hadFocus) pager.querySelector('.page-btn.active')?.focus();

  pager.querySelectorAll('.page-btn:not([disabled])').forEach(btn => {
    btn.addEventListener('click', () => onGo(Number(btn.dataset.page)));
  });
}

/** 입력이 멈춘 뒤 한 번만 실행한다. */
function debounce(fn, ms = 250) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

/** 난이도 그룹 키를 tier 범위로 푼다. 경계 정의는 TIER_GROUPS 한 곳뿐이다.
 *  그룹은 solved.ac 티어 1~30 체계라 platform 을 boj 로 함께 고정한다. */
function tierGroupParams(key) {
  const r = TIER_GROUPS[key];
  if (!r) return {};
  return { tier_min: r[0], tier_max: r[1], platform: 'boj' };
}

/** 저장된 시각 문자열을 Date 로. 오프셋이 없으면 UTC 로 본다
 *  (서버 `timestamps.parse_stored` 와 같은 규칙). JS 는 오프셋 없는 ISO 를 로컬 시각으로 읽는다. */
function parseStoredTime(value) {
  const s = String(value || '').trim();
  if (!s) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(s);
  const d = new Date(hasZone ? s : `${s}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** 보는 사람의 시간대 기준 `YYYY-MM-DD`. 저장값은 UTC 라 문자열을 자르면 안 된다. */
function localDate(value) {
  const d = parseStoredTime(value);
  if (!d) return '';
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 객체를 쿼리스트링으로. 빈 값은 뺀다(서버 기본값 사용). */
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
  // href 에 들어가므로 http(s) 만 통과시킨다 — escapeHtml 은 `javascript:` 를 막지 못한다.
  if (/^https?:\/\//i.test(problem.problem_url || '')) return problem.problem_url;
  if (problem.platform === 'codeforces') {
    // 파싱 실패 시에도 BOJ 로 흘려보내지 않는다.
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
    btn.innerHTML =
      `<span class="spinner spinner-sm"></span> ${escapeHtml(btn.dataset.loadingLabel || '처리 중...')}`;
  } else {
    // dataset.label 은 평문이라 textContent 로 되돌린다.
    btn.textContent = btn.dataset.label;
  }
}

function showError(container, msg) {
  // 먼저 보이게 한 뒤 내용을 넣는다 — display:none 중의 변경은 aria-live 가 읽지 않는다.
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
    // JSON 이 아닌 응답(프록시 오류 페이지 등) — 본문 앞머리를 함께 보여준다.
    throw new Error(`응답 형식 오류(${res.status}): ${text.slice(0, 100)}`);
  }
  // 422 의 detail 은 객체 배열이라 errorDetail 로 편다.
  if (!res.ok) throw new Error(errorDetail(data) || fallbackMsg);
  return data;
}

function errorDetail(data) {
  const d = data && data.detail;
  if (Array.isArray(d)) return d.map(e => (e && e.msg) || '').filter(Boolean).join(' / ');
  return typeof d === 'string' ? d : '';
}

/** 마크다운을 안전한 HTML 로. CDN(marked·DOMPurify)이 막히면 평문으로 폴백한다. */
function renderMarkdown(text) {
  const raw = text || '';
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
    return `<pre class="code-block">${escapeHtml(raw)}</pre>`;
  }
  return DOMPurify.sanitize(marked.parse(raw));
}

/** div 를 버튼처럼 쓰는 곳에 role·tabindex·키보드 핸들러를 함께 건다. */
function makeRowActivatable(el, onActivate) {
  el.setAttribute('role', 'button');
  el.setAttribute('tabindex', '0');

  // 행 안의 링크·버튼은 자기 동작을 한다.
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

// 코드 본문에서 제출 언어를 추론한다. 반환값 도메인은 #code-language 의 option value 와
// 같고, 맞는 것이 없으면 '' 다. 순서가 규칙이다 — 좁은 마커가 먼저, 공유 마커가 나중.
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
  // 3) Ruby 는 C 뒤. `puts(…)`·`gets(…)` 는 C 표준 함수이기도 해 괄호 없는 관용형만 본다.
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
