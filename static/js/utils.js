const TIER_GROUPS = {
  bronze: [1, 5], silver: [6, 10], gold: [11, 15],
  platinum: [16, 20], diamond: [21, 25], ruby: [26, 30], unrated: [0, 0],
};

function tierInGroup(tier, key) {
  const r = TIER_GROUPS[key];
  return tier >= r[0] && tier <= r[1];
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
    const url = cfRefToUrl(problem.problem_ref);
    if (url) return url;
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
  container.innerHTML = `<div class="alert alert-error">${escapeHtml(msg)}</div>`;
  container.classList.remove('hidden');
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
  el.addEventListener('click', onActivate);
  el.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
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
