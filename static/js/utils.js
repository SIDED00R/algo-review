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

/** 난이도 그룹 판정. **BOJ 전용**이다 — 그룹 경계가 solved.ac 티어 1~30 체계다.
 *  CF 행은 tier 가 항상 0 이라(레이팅은 tier_name 에만 있다) 걸러 두지 않으면
 *  "Unrated" 선택에 CF 문제가 전량 딸려 온다. */
function tierInGroup(tier, key, platform) {
  if (platform && platform !== 'boj') return false;
  const r = TIER_GROUPS[key];
  return tier >= r[0] && tier <= r[1];
}

/** 난이도 필터 <option> 목록. 두 벌로 두면 갈린다 — 실제로 리뷰 기록 탭에는 Ruby·Unrated
 *  가 빠져 있어 그 두 그룹을 난이도로 걸러낼 수 없었다. */
function tierFilterOptionsHtml() {
  return ['<option value="">전체 난이도</option>']
    .concat(Object.keys(TIER_GROUPS).map(
      key => `<option value="${key}">${TIER_GROUP_LABELS[key]}</option>`))
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

// 리뷰 기록 검색과 ⌘K 팔레트가 같은 판정을 쓴다 — 술어를 두 벌로 만들면
// 한쪽만 고쳐졌을 때 같은 질의가 다른 결과를 준다.
function matchesProblemQuery(problem, query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return true;
  const hay = `${problemLabel(problem)} ${problem.title || ''} ${(problem.tags || []).join(' ')}`;
  return hay.toLowerCase().includes(q);
}

function compareProblemLabel(a, b) {
  return problemLabel(a).localeCompare(problemLabel(b), undefined, { numeric: true });
}

function cfRefToUrl(ref) {
  const m = String(ref || '').replace(/[^0-9A-Za-z]/g, '').match(/^(\d+)([A-Za-z][A-Za-z0-9]*)$/);
  return m ? `https://codeforces.com/problemset/problem/${m[1]}/${m[2].toUpperCase()}` : '';
}

function problemUrl(problem) {
  if (problem.problem_url) return problem.problem_url;
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
 *  예전에는 무가드라 ReferenceError 가 나고, 서버가 이미 저장·과금한 리뷰 결과가
 *  화면에서 통째로 사라졌다. Chart·KaTeX 는 이미 같은 가드가 있다. */
function renderMarkdown(text) {
  const raw = text || '';
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
    return `<pre class="code-block">${escapeHtml(raw)}</pre>`;
  }
  return DOMPurify.sanitize(marked.parse(raw));
}

/** div 를 버튼처럼 쓰는 곳에 키보드 접근을 준다. role/tabindex 만 붙여도 Enter/Space 가
 *  동작하지 않으므로 핸들러까지 함께 건다 — 예전에는 마우스로만 열 수 있었다. */
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

function detectLanguage(code) {
  if (/#include/.test(code) || /\bstd::/.test(code) || /\bcout\b/.test(code) ||
      /\bcin\b/.test(code) || /\bint\s+main\s*\(/.test(code) || /\bvector\s*</.test(code) ||
      /\busing\s+namespace\s+std/.test(code)) return 'GNU C++17';
  if (/\bdef\s+\w/.test(code) || /\bimport\s+\w/.test(code) ||
      /\bprint\s*\(/.test(code) || /\binput\s*\(/.test(code) ||
      /\brange\s*\(/.test(code)) return 'Python 3';
  if (/\bpublic\s+class\b/.test(code) || /\bSystem\.out\b/.test(code) ||
      /\bScanner\b/.test(code) || /\bBufferedReader\b/.test(code)) return 'Java';
  if (/\bfun\s+main\b/.test(code) || /\bprintln\b/.test(code) ||
      /\breadLine\b/.test(code)) return 'Kotlin';
  if (/\busing\s+System\b/.test(code) || /\bConsole\.\w/.test(code)) return 'C#';
  if (/\bfn\s+main\s*\(/.test(code) || /\buse\s+std::io/.test(code) ||
      /\blet\s+mut\b/.test(code)) return 'Rust';
  if (/\bpackage\s+main\b/.test(code) || /\bfmt\./.test(code)) return 'Go';
  if (/\brequire\s*\(/.test(code) || /\bconsole\.log\b/.test(code)) return 'JavaScript';
  if (/\bprintf\s*\(/.test(code) || /\bscanf\s*\(/.test(code)) return 'C';
  return '';
}
