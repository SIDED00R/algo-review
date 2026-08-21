// 테마별 문제 탭 — 플랫폼(Codeforces/백준) 토글 + 테마 칩 선택 + 3계층 캐시(메모리/localStorage/서버).
let themesPlatform = 'codeforces';
let selectedThemeId = null;
let _themeList = null;                    // [{id, label}]
const _themeProblemsCache = new Map();    // 'codeforces:dp' → 테마 문제 응답

const _LS_LIST_KEY = 'themes:list:v1';
const _LS_LIST_TTL_MS = 24 * 60 * 60 * 1000;
const _LS_PROBLEMS_TTL_MS = 30 * 60 * 1000;

function _lsGet(key, ttlMs) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const { savedAt, data } = JSON.parse(raw);
    return (Date.now() - savedAt > ttlMs) ? null : data;
  } catch { return null; }
}

function _lsSet(key, data) {
  try {
    localStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data }));
  } catch { /* 프라이빗 모드/용량 초과 시 무시 — 메모리 캐시만으로 동작 */ }
}

async function ensureThemeList() {
  if (_themeList) return _themeList;
  const cached = _lsGet(_LS_LIST_KEY, _LS_LIST_TTL_MS);
  if (cached) { _themeList = cached; return _themeList; }
  const data = await fetchJsonOk('/api/themes', undefined, '테마 목록 로딩 실패');
  _themeList = data.themes || [];
  _lsSet(_LS_LIST_KEY, _themeList);
  return _themeList;
}

async function loadThemes() {
  const result = document.getElementById('themes-result');
  try {
    await ensureThemeList();
  } catch (e) {
    showError(result, e.message);
    return;
  }
  renderThemeChips();
  if (selectedThemeId) {
    loadThemeProblems();
  } else {
    result.innerHTML = '<div class="alert alert-info">테마를 선택하면 문제가 표시됩니다.</div>';
  }
}

function renderThemeChips() {
  const box = document.getElementById('themes-chips');
  box.innerHTML = _themeList.map(t =>
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
  _lsSet(`themes:problems:v1:${key}`, data);
}

async function loadThemeProblems({ force = false } = {}) {
  const result = document.getElementById('themes-result');
  const key = `${themesPlatform}:${selectedThemeId}`;

  if (!force) {
    const mem = _themeProblemsCache.get(key);
    if (mem) { renderThemeProblems(result, mem); return; }
    const ls = _lsGet(`themes:problems:v1:${key}`, _LS_PROBLEMS_TTL_MS);
    if (ls) {
      _themeProblemsCache.set(key, ls);
      renderThemeProblems(result, ls);
      return;
    }
  }

  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 문제를 불러오는 중입니다...</div>';
  try {
    const data = await _fetchThemeProblems(themesPlatform, selectedThemeId);
    _cacheThemeProblems(key, data);
    renderThemeProblems(result, data);
  } catch (e) {
    showError(result, e.message);
  }
}

function renderThemeProblems(container, data) {
  const problems = data.problems || [];
  const label = data.theme ? data.theme.label : '';
  const isCf = data.platform === 'codeforces';

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
      if (isCf) {
        // CF 문제는 인앱 뷰어로 — 난이도는 네이티브 레이팅(*1300) 표기.
        html += `
        <div class="rec-problem-card is-clickable"
             data-ref="${escapeHtml(String(p.id))}"
             data-title="${escapeHtml(p.title)}"
             data-tier="*${escapeHtml(String(p.rating))}">
          <span>${escapeHtml(String(p.id))}. ${escapeHtml(p.title)}</span>
          <span class="tier-badge ${cfRatingClass(p.rating)}">*${escapeHtml(String(p.rating))}</span>
        </div>`;
      } else {
        // 백준 본체(acmicpc)가 서비스 종료라 링크 없이 정보만 표시한다.
        html += `
        <div class="rec-problem-card">
          <span>${escapeHtml(String(p.id))}. ${escapeHtml(p.title)}</span>
          ${tierBadgeHtml(tierClass(p.tier), escapeHtml(p.tier_name))}
        </div>`;
      }
    }
    html += '</div>';
  }
  html += '</div>';
  container.innerHTML = html;

  document.getElementById('themes-refresh-btn')
    .addEventListener('click', () => loadThemeProblems({ force: true }));
  bindCfProblemClicks(container);
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
    if (selectedThemeId) loadThemeProblems();
  });
});

// 유휴 프리페치 — 접속 직후 기본 플랫폼의 테마 문제를 백그라운드로 순차 워밍해 탭 진입을 즉시로 만든다.
async function prefetchThemeData() {
  await ensureThemeList();
  for (const t of _themeList) {
    const key = `${themesPlatform}:${t.id}`;
    if (_themeProblemsCache.has(key) || _lsGet(`themes:problems:v1:${key}`, _LS_PROBLEMS_TTL_MS)) continue;
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
