// 요청 세대 토큰. 이 로더는 탭 전환(화살표 키 이동마다 발생)과 가져오기 3종 완료에서
// 불려 겹쳐 실행된다. 늦게 끝난 호출이 목록을 다시 그리면 그때 붙는 핸들러가 자기
// 클로저의 allProblems 를 잡고, 이후 삭제가 화면에 남은 다른 클로저에 반영되지 않는다.
let _importToken = 0;

// 진행 중인 AI 리뷰의 `platform-ref` 집합. 진행 중 상태를 버튼 노드에만 두면 검색·정렬·
// 페이지 이동이 목록을 innerHTML 로 교체할 때 사라져, 같은 문제에 유료 호출이 두 번 나간다.
const _reviewing = new Set();

async function loadImportedHistory() {
  const list = document.getElementById('import-history-list');
  if (!list) return;
  const token = ++_importToken;
  let data;
  try {
    data = await fetchJsonOk('/api/solved-history', undefined, '가져온 기록 로딩 실패');
  } catch (e) {
    if (token !== _importToken) return;
    showError(list, e.message);
    return;
  }
  if (token !== _importToken) return;

  if (!data.problems || data.problems.length === 0) {
    list.innerHTML = '<div class="alert alert-info">가져온 기록이 없습니다.</div>';
    return;
  }
  const allProblems = data.problems;
  const myToken = token;   // 이 클로저가 그린 목록의 세대
  list.innerHTML = `
    <div class="card">
      <div class="toolbar">
        <h3 class="section-title section-title-flush">
          가져온 풀이 기록 (<span id="import-count">${allProblems.length}</span>개 표시 중)
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

  let importPage = 1;
  let importPerPage = 20;

  function getFiltered() {
    const q = document.getElementById('import-search').value;
    const platform = document.getElementById('import-platform-filter').value;
    const tierKey = document.getElementById('import-tier-filter').value;
    const sort = document.getElementById('import-sort').value;

    const result = allProblems.filter(p => {
      // 리뷰 기록 검색·⌘K 팔레트와 같은 술어를 쓴다 — 세 벌로 만들면 한쪽만 고쳐졌을 때
      // 같은 질의가 탭마다 다른 결과를 준다. (solved 행에는 tags 가 없어도 안전하다)
      if (!matchesProblemQuery(p, q)) return false;
      if (platform && (p.platform || 'boj') !== platform) return false;
      if (tierKey && !tierInGroup(p.tier, tierKey, p.platform)) return false;
      return true;
    });

    result.sort((a, b) => {
      if (sort === 'id-asc') return compareProblemLabel(a, b);
      if (sort === 'id-desc') return compareProblemLabel(b, a);
      if (sort === 'tier-desc') return b.tier - a.tier;
      if (sort === 'tier-asc') return a.tier - b.tier;
      // 기본값 date-desc — 서버가 imported_at 내림차순으로 주고 Array.sort 가 안정적이라
      // 0 을 돌려주면 그 순서가 유지된다(의도를 코드에 남긴다).
      return 0;
    });
    return result;
  }

  function renderPagination(totalItems) {
    const totalPages = Math.max(1, Math.ceil(totalItems / importPerPage));
    importPage = Math.min(importPage, totalPages);
    const pager = document.getElementById('import-pager');

    let html = `<button class="page-btn" ${importPage === 1 ? 'disabled' : ''} data-page="${importPage - 1}">‹</button>`;
    let start = Math.max(1, importPage - 3);
    let end = Math.min(totalPages, start + 6);
    if (end - start < 6) start = Math.max(1, end - 6);

    if (start > 1) html += `<button class="page-btn" data-page="1">1</button>${start > 2 ? '<span class="page-ellipsis">…</span>' : ''}`;
    for (let i = start; i <= end; i++) {
      html += `<button class="page-btn ${i === importPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }
    if (end < totalPages) html += `${end < totalPages - 1 ? '<span class="page-ellipsis">…</span>' : ''}<button class="page-btn" data-page="${totalPages}">${totalPages}</button>`;
    html += `<button class="page-btn" ${importPage === totalPages ? 'disabled' : ''} data-page="${importPage + 1}">›</button>`;
    pager.innerHTML = html;

    pager.querySelectorAll('.page-btn:not([disabled])').forEach(btn => {
      btn.addEventListener('click', () => {
        importPage = Number(btn.dataset.page);
        renderImportCards(getFiltered());
      });
    });
  }

  function renderImportCards(filtered) {
    const container = document.getElementById('import-cards');
    document.getElementById('import-count').textContent = filtered.length;

    if (!filtered.length) {
      container.innerHTML = '<div class="hint pad-y">검색 결과가 없습니다.</div>';
      renderPagination(0);
      return;
    }

    const totalPages = Math.ceil(filtered.length / importPerPage);
    importPage = Math.min(importPage, Math.max(1, totalPages));
    const pageItems = filtered.slice((importPage - 1) * importPerPage, importPage * importPerPage);

    container.innerHTML = pageItems.map(p => {
      const tc = tierClass(p.tier);
      const cardKey = `${p.platform || 'boj'}-${p.problem_ref || p.problem_id}`;
      const platformBadge = (p.platform || 'boj') === 'codeforces' ? 'Codeforces' : 'BOJ';
      const actionBtns = p.has_code
        ? `<button class="btn-sm btn-code btn-view-code" data-platform="${escapeHtml(p.platform || 'boj')}" data-problem-ref="${escapeHtml(p.problem_ref || p.problem_id)}" data-box-key="${escapeHtml(cardKey)}">코드 보기</button>
           <button class="btn-sm btn-ai btn-review-imported" data-platform="${escapeHtml(p.platform || 'boj')}" data-problem-ref="${escapeHtml(p.problem_ref || p.problem_id)}"${_reviewing.has(`${p.platform || 'boj'}-${p.problem_ref || p.problem_id}`) ? ' disabled' : ''}>AI 리뷰</button>`
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

    renderPagination(filtered.length);
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

  document.getElementById('import-per-page').addEventListener('change', e => {
    importPerPage = Number(e.target.value);
    importPage = 1;
    renderImportCards(getFiltered());
  });

  // 클로저 안에 둔다 — 톱레벨에 있으면 allProblems 에 접근할 수 없어 DOM 만 지우게 되고,
  // 서버는 행을 실제로 삭제하므로 필터를 한 번 만지면 삭제된 항목이 되살아난다.
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
      if (myToken === _importToken) renderImportCards(getFiltered());
      alert('오류: ' + e.message);
      return;
    }
    _reviewing.delete(key);

    // 이 목록이 아직 화면에 있는 목록일 때만 손댄다. 늦게 끝난 호출이 자기 클로저의
    // allProblems 를 다시 그리면 그 사이 새로 불러온 목록이 옛 스냅샷으로 되돌아간다.
    if (myToken !== _importToken) return;

    // 서버가 지운 행을 목록 데이터에서도 뺀다. 그 뒤 재렌더로 개수·페이지가 함께 맞는다.
    const idx = allProblems.findIndex(p => `${p.platform || 'boj'}-${p.problem_ref || p.problem_id}` === key);
    if (idx !== -1) allProblems.splice(idx, 1);

    if (!allProblems.length) {
      list.innerHTML = '<div class="alert alert-info">가져온 기록이 없습니다.</div>';
      return;
    }
    renderImportCards(getFiltered());
  }

  renderImportCards(getFiltered());

  ['import-search', 'import-platform-filter', 'import-tier-filter', 'import-sort'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
      importPage = 1;
      renderImportCards(getFiltered());
    });
  });

}
