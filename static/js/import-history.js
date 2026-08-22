// 요청 세대 토큰. 이 로더는 탭 전환(화살표 키 이동마다 발생)과 가져오기 3종 완료에서
// 불려 겹쳐 실행된다. 늦게 끝난 호출이 목록을 다시 그리면 그때 붙는 핸들러가 자기
// 클로저의 목록을 잡고, 이후 삭제가 화면에 남은 다른 클로저에 반영되지 않는다.
let _importToken = 0;

// 진행 중인 AI 리뷰의 `platform-ref` 집합. 진행 중 상태를 버튼 노드에만 두면 검색·정렬·
// 페이지 이동이 목록을 innerHTML 로 교체할 때 사라져, 같은 문제에 유료 호출이 두 번 나간다.
const _reviewing = new Set();

// 목록은 서버가 걸러 준다 — 전 행을 받아 클라이언트에서 거르면 응답이 기록 수에 비례해
// 자라고(5천 행에서 1.07MB), 그 스냅샷을 잡은 클로저가 늦게 끝나 화면을 되돌린다.
let _importPage = 1;
let _importPerPage = 20;
let _importTotal = 0;

function importQuery() {
  const tierKey = document.getElementById('import-tier-filter')?.value || '';
  const params = {
    q: document.getElementById('import-search')?.value || '',
    sort: document.getElementById('import-sort')?.value || 'date-desc',
    page: _importPage,
    per_page: _importPerPage,
    ...tierGroupParams(tierKey),
  };
  // 난이도 그룹은 BOJ 전용이라 platform 을 고정한다 — 그때는 플랫폼 필터가 덮지 않는다.
  if (!params.platform) {
    params.platform = document.getElementById('import-platform-filter')?.value || '';
  }
  return listQuery(params);
}

function hasImportFilter() {
  return ['import-search', 'import-platform-filter', 'import-tier-filter']
    .some(id => (document.getElementById(id)?.value || ''));
}

async function loadImportedHistory() {
  const list = document.getElementById('import-history-list');
  if (!list) return;
  _importPage = 1;
  renderImportShell(list);
  await refreshImportList();
}

function renderImportShell(list) {
  list.innerHTML = `
    <div class="card">
      <div class="toolbar">
        <h3 class="section-title section-title-flush">
          가져온 풀이 기록 (<span id="import-count">0</span>개)
        </h3>
        <input id="import-search" class="input filter-grow" type="text" aria-label="가져온 기록 검색"
               placeholder="문제번호 또는 제목 검색..." />
        <select id="import-platform-filter" class="select filter-fixed" aria-label="플랫폼 필터">
          <option value="">전체 플랫폼</option>
          <option value="boj">BOJ</option>
          <option value="codeforces">Codeforces</option>
        </select>
        <select id="import-tier-filter" class="select filter-fixed" aria-label="난이도 필터">
          ${tierFilterOptionsHtml()}
        </select>
        <select id="import-per-page" class="select filter-fixed" aria-label="페이지당 개수">
          <option value="10">10개</option>
          <option value="20" selected>20개</option>
          <option value="50">50개</option>
        </select>
        <select id="import-sort" class="select filter-fixed" aria-label="정렬">
          <option value="date-desc">최근 가져온 순</option>
          <option value="id-asc">번호 오름차순</option>
          <option value="id-desc">번호 내림차순</option>
          <option value="tier-desc">난이도 높은 순</option>
          <option value="tier-asc">난이도 낮은 순</option>
        </select>
      </div>
      <div id="import-cards"></div>
      <div id="import-pager" class="pager"></div>
    </div>`;

  // 필터가 바뀌면 첫 페이지부터 다시 받는다. 입력마다 서버를 치지 않도록 묶는다.
  const reload = debounce(() => { _importPage = 1; refreshImportList(); });
  ['import-search', 'import-platform-filter', 'import-tier-filter', 'import-sort']
    .forEach(id => document.getElementById(id).addEventListener('input', reload));
  document.getElementById('import-per-page').addEventListener('change', e => {
    _importPerPage = Number(e.target.value);
    _importPage = 1;
    refreshImportList();
  });
}

async function refreshImportList() {
  const token = ++_importToken;
  const container = document.getElementById('import-cards');
  if (!container) return;

  let data;
  try {
    data = await fetchJsonOk(`/api/solved-history?${importQuery()}`,
                             undefined, '가져온 기록 로딩 실패');
  } catch (e) {
    if (token !== _importToken) return;
    container.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
    return;
  }
  if (token !== _importToken) return;

  _importTotal = data.total || 0;
  document.getElementById('import-count').textContent = _importTotal;
  renderImportCards(container, data.problems || []);
  renderPager(document.getElementById('import-pager'), _importPage,
              Math.max(1, Math.ceil(_importTotal / _importPerPage)),
              page => { _importPage = page; refreshImportList(); });
}

function renderImportCards(container, problems) {
  if (!problems.length) {
    container.innerHTML = hasImportFilter()
      ? '<div class="hint pad-y">검색 결과가 없습니다.</div>'
      : '<div class="alert alert-info">가져온 기록이 없습니다.</div>';
    return;
  }

  container.innerHTML = problems.map(p => {
    const tc = tierClass(p.tier);
    const cardKey = `${p.platform || 'boj'}-${p.problem_ref || p.problem_id}`;
    const platformBadge = (p.platform || 'boj') === 'codeforces' ? 'Codeforces' : 'BOJ';
    const actionBtns = p.has_code
      ? `<button class="btn-sm btn-code btn-view-code" data-platform="${escapeHtml(p.platform || 'boj')}" data-problem-ref="${escapeHtml(p.problem_ref || p.problem_id)}" data-box-key="${escapeHtml(cardKey)}">코드 보기</button>
         <button class="btn-sm btn-ai btn-review-imported" data-platform="${escapeHtml(p.platform || 'boj')}" data-problem-ref="${escapeHtml(p.problem_ref || p.problem_id)}"${_reviewing.has(cardKey) ? ' disabled' : ''}>AI 리뷰</button>`
      : `<span class="hint">코드 없음</span>`;
    return `
      <div class="row row-static">
        <div class="row-main">
          <div class="row-title">
            <a href="${escapeHtml(problemUrl(p))}" target="_blank" rel="noopener noreferrer">
              ${escapeHtml(problemLabel(p))}. ${escapeHtml(p.title)}
            </a>
          </div>
          <div class="row-meta">${escapeHtml(platformBadge)}${p.language ? ` · ${escapeHtml(p.language)}` : ''}</div>
        </div>
        <div class="row-side">
          ${tierBadgeHtml(tc, escapeHtml(p.tier_name || ''))}
          ${actionBtns}
          <span class="row-dim">${escapeHtml(String(p.imported_at || '').slice(0, 10))}</span>
        </div>
      </div>
      <div id="code-view-${escapeHtml(cardKey)}" class="hidden"></div>`;
  }).join('');

  container.querySelectorAll('.btn-view-code').forEach(btn => {
    btn.addEventListener('click', () => toggleCodeView(btn));
  });
  container.querySelectorAll('.btn-review-imported').forEach(btn => {
    btn.addEventListener('click', () => requestImportedReview(btn));
  });
}

async function toggleCodeView(btn) {
  const platform = btn.dataset.platform;
  const problemRef = btn.dataset.problemRef;
  const box = document.getElementById(`code-view-${btn.dataset.boxKey}`);
  if (!box.classList.contains('hidden')) {
    box.classList.add('hidden');
    btn.textContent = '코드 보기';
    return;
  }
  btn.textContent = '닫기';
  if (box.dataset.loaded) { box.classList.remove('hidden'); return; }

  box.innerHTML = '<div class="hint pad-y"><span class="spinner"></span> 불러오는 중...</div>';
  box.classList.remove('hidden');

  try {
    const data = await fetchJsonOk(
      `/api/solved-history/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`,
      undefined, '코드 불러오기 실패');
    const code = data.code || '';
    // loaded 는 성공했을 때만 세운다 — 실패에도 세우면 오류 상태가 영구 캐시돼
    // 다시 눌러도 재시도되지 않는다.
    box.dataset.loaded = '1';
    box.innerHTML = code
      ? `<pre class="code-block code-inline-view">${escapeHtml(code)}</pre>`
      : `<div class="hint pad-y">저장된 코드가 없습니다.</div>`;
  } catch (e) {
    box.innerHTML = `<div class="hint hint-bad pad-y">${escapeHtml(e.message)}</div>`;
  }
}

// 목록 데이터를 클로저에 잡지 않는다 — 서버가 정본이라 완료 후 그 페이지를 다시 받으면
// 개수·페이지가 함께 맞는다. 클로저를 잡으면 늦게 끝난 호출이 옛 스냅샷을 되살린다.
async function requestImportedReview(btn) {
  const platform = btn.dataset.platform;
  const problemRef = btn.dataset.problemRef;
  const key = `${platform}-${problemRef}`;
  if (_reviewing.has(key)) return;
  _reviewing.add(key);
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  try {
    await fetchJsonOk(
      `/api/review-imported/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`,
      { method: 'POST' }, 'AI 리뷰 실패');
  } catch (e) {
    _reviewing.delete(key);
    await refreshImportList();
    alert('오류: ' + e.message);
    return;
  }
  _reviewing.delete(key);
  await refreshImportList();
}
