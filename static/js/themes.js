// 테마별 문제 탭 — 플랫폼(Codeforces/백준) 토글 + 테마 칩 선택 + 3계층 캐시(메모리/localStorage/서버).
let themesPlatform = 'codeforces';
let selectedThemeId = null;
const _themeLists = {};                   // platform → [{id, label}] — 테마 목록은 플랫폼마다 다르다(SQL 은 LeetCode 뿐)
const _themeProblemsCache = new Map();    // 'codeforces:dp' → 테마 문제 응답

const _LS_LIST_TTL_MS = 24 * 60 * 60 * 1000;
const _LS_PROBLEMS_TTL_MS = 30 * 60 * 1000;

function _lsGet(key, ttlMs) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const { savedAt, data } = JSON.parse(raw);
    // savedAt 이 없으면 `Date.now() - undefined` 가 NaN 이고 `NaN > ttl` 은 false 라
    // 손상된 항목이 영원히 신선으로 판정된다.
    if (typeof savedAt !== 'number') return null;
    return (Date.now() - savedAt > ttlMs) ? null : data;
  } catch { return null; }
}

function _lsSet(key, data) {
  try {
    localStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data }));
  } catch { /* 프라이빗 모드/용량 초과 시 무시 — 메모리 캐시만으로 동작 */ }
}

async function ensureThemeList() {
  const platform = themesPlatform;
  if (_themeLists[platform]) return _themeLists[platform];
  const lsKey = `themes:list:v2:${platform}`;
  const cached = _lsGet(lsKey, _LS_LIST_TTL_MS);
  if (cached) { _themeLists[platform] = cached; return cached; }
  const data = await fetchJsonOk(`/api/themes?platform=${encodeURIComponent(platform)}`, undefined, '테마 목록 로딩 실패');
  _themeLists[platform] = data.themes || [];
  _lsSet(lsKey, _themeLists[platform]);
  return _themeLists[platform];
}

async function loadThemes() {
  const result = document.getElementById('themes-result');
  let list;
  try {
    list = await ensureThemeList();
  } catch (e) {
    showError(result, e.message);
    return;
  }
  // 플랫폼을 바꾸면 고른 테마가 새 목록에 없을 수 있다(SQL → 백준). 첫 테마로 옮긴다.
  if (selectedThemeId && !list.some(t => t.id === selectedThemeId)) {
    selectedThemeId = list[0]?.id || null;
  }
  renderThemeChips(list);
  if (selectedThemeId) {
    loadThemeProblems();
  } else {
    result.innerHTML = '<div class="alert alert-info">테마를 선택하면 문제가 표시됩니다.</div>';
  }
}

function renderThemeChips(list) {
  const box = document.getElementById('themes-chips');
  box.innerHTML = list.map(t =>
    `<button class="theme-chip${t.id === selectedThemeId ? ' active' : ''}" data-theme-id="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`
  ).join('');
  box.querySelectorAll('.theme-chip').forEach(btn => {
    btn.addEventListener('click', () => selectTheme(btn.dataset.themeId));
  });
}

function selectTheme(themeId) {
  selectedThemeId = themeId;
  document.querySelectorAll('#themes-chips .theme-chip').forEach(b =>
    b.classList.toggle('active', b.dataset.themeId === themeId));
  loadThemeProblems();
}

async function _fetchThemeProblems(platform, themeId) {
  return fetchJsonOk(`/api/themes/${encodeURIComponent(themeId)}/problems?platform=${platform}`, undefined, '문제 로딩 실패');
}

function _cacheThemeProblems(key, data) {
  // 실패 응답(error 필드)은 캐시하지 않는다 — 다음 시도에서 다시 서버로.
  if (data.error) return;
  _themeProblemsCache.set(key, data);
  _lsSet(`themes:problems:v2:${key}`, data);
}

// 요청 세대 토큰 — 테마 A 를 고른 직후 B 를 누르면 A 의 늦은 응답이 B 의 렌더를 덮어
// 칩은 B 가 활성인데 제목은 A 가 표시된다(problem-modal.js 와 같은 규약).
let _themeToken = 0;

async function loadThemeProblems({ force = false } = {}) {
  const result = document.getElementById('themes-result');
  const key = `${themesPlatform}:${selectedThemeId}`;
  const token = ++_themeToken;

  if (!force) {
    const mem = _themeProblemsCache.get(key);
    if (mem) { renderThemeProblems(result, mem); return; }
    const ls = _lsGet(`themes:problems:v2:${key}`, _LS_PROBLEMS_TTL_MS);
    if (ls) {
      _themeProblemsCache.set(key, ls);
      renderThemeProblems(result, ls);
      return;
    }
  }

  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 문제를 불러오는 중입니다...</div>';
  try {
    const data = await _fetchThemeProblems(themesPlatform, selectedThemeId);
    // 캐시는 키가 있어 늦은 응답이어도 안전하다 — 렌더만 막는다.
    _cacheThemeProblems(key, data);
    if (token !== _themeToken) return;
    renderThemeProblems(result, data);
  } catch (e) {
    if (token !== _themeToken) return;
    showError(result, e.message);
  }
}

function renderThemeProblems(container, data) {
  const problems = data.problems || [];
  const label = data.theme ? data.theme.label : '';
  const spec = platformSpec(data.platform);

  let html = '<div class="result-card">';
  html += `
    <div class="themes-list-header">
      <span class="rec-tag-title rec-tag-title-flush">${escapeHtml(label)}</span>
      <button id="themes-refresh-btn" class="btn-toggle">새로고침</button>
    </div>`;

  if (data.error) {
    html += `<div class="alert alert-error">${escapeHtml(data.error)}</div>`;
  } else if (problems.length === 0) {
    html += '<div class="alert alert-info">표시할 문제가 없습니다. 이미 푼 문제는 제외됩니다.</div>';
  } else {
    html += '<div class="rec-problems">';
    for (const p of problems) {
      // CF 문제는 레이팅(*1300) 배지, 나머지는 tier·tier_name 배지 — 응답 항목의 필드로 갈린다.
      const badge = p.rating != null
        ? `<span class="tier-badge ${cfRatingClass(p.rating)}">*${escapeHtml(String(p.rating))}</span>`
        : tierBadgeHtml(difficultyClass(data.platform, p.tier), escapeHtml(p.tier_name));
      const tierLabel = p.rating != null ? `*${p.rating}` : p.tier_name;
      const label = escapeHtml(problemLabel({
        platform: data.platform, problem_id: p.problem_id, problem_ref: String(p.id),
      }));
      if (spec.viewer) {
        html += `
        <div class="rec-problem-card is-clickable"
             data-platform="${escapeHtml(data.platform)}"
             data-ref="${escapeHtml(String(p.id))}"
             data-title="${escapeHtml(p.title)}"
             data-tier="${escapeHtml(String(tierLabel))}">
          <span>${label}. ${escapeHtml(p.title)}</span>
          ${badge}
        </div>`;
      } else {
        // 백준 본체(acmicpc)가 서비스 종료라 링크 없이 정보만 표시한다.
        html += `
        <div class="rec-problem-card">
          <span>${label}. ${escapeHtml(p.title)}</span>
          ${badge}
        </div>`;
      }
    }
    html += '</div>';
  }
  html += '</div>';
  container.innerHTML = html;

  document.getElementById('themes-refresh-btn')
    .addEventListener('click', () => loadThemeProblems({ force: true }));
  bindProblemClicks(container);
}

// 플랫폼 토글 — stats.js가 문서 전역 [data-platform]을 바인딩하므로 별도 속성(data-themes-platform)을 쓴다.
document.querySelectorAll('.btn-toggle[data-themes-platform]').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.themesPlatform === themesPlatform) return;
    document.querySelectorAll('.btn-toggle[data-themes-platform]').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-pressed', 'false');
    });
    btn.classList.add('active');
    btn.setAttribute('aria-pressed', 'true');
    themesPlatform = btn.dataset.themesPlatform;
    // 목록이 플랫폼마다 달라 칩도 다시 그린다.
    loadThemes();
  });
});

// 유휴 프리페치 — 접속 직후 기본 플랫폼의 테마 문제를 백그라운드로 순차 워밍해 탭 진입을 즉시로 만든다.
async function prefetchThemeData() {
  const list = await ensureThemeList();
  for (const t of list) {
    const key = `${themesPlatform}:${t.id}`;
    if (_themeProblemsCache.has(key) || _lsGet(`themes:problems:v2:${key}`, _LS_PROBLEMS_TTL_MS)) continue;
    try {
      _cacheThemeProblems(key, await _fetchThemeProblems(themesPlatform, t.id));
    } catch { /* 프리페치 실패는 무시 — 탭 진입 시 재시도 */ }
  }
}

window.addEventListener('load', () => {
  const idle = window.requestIdleCallback
    ? (cb) => requestIdleCallback(cb, { timeout: 5000 })
    : (cb) => setTimeout(cb, 2500);
  idle(() => { prefetchThemeData().catch(() => {}); });
});
