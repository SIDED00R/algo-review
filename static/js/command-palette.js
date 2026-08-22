// ⌘K 팔레트 — 탭 이동과 '지난 제출 불러오기'.
// 내부 이름이 많아 IIFE 로 감싼다(최상위 const 이름이 겹치면 전체 스크립트가 죽는다).
(function () {
  const TABS = [
    ['review', '코드 리뷰'], ['recommend', '문제 추천'], ['themes', '테마별 문제'],
    ['stats', '통계'], ['report', '종합 리포트'], ['history', '리뷰 기록'],
    ['import', '기록 가져오기'],
  ];

  const overlay = document.getElementById('cmdk');
  if (!overlay) return;
  const input = document.getElementById('cmdk-input');
  const listEl = document.getElementById('cmdk-list');
  const crumbEl = document.getElementById('cmdk-crumb');

  let mode = 'root';        // root | problems | ledger
  let rows = [];            // 실행 가능한 항목만 [{label, meta, run}]
  // 실행할 수 없는 안내 한 줄. rows 에 섞으면 ↑↓ 가 멈추는 죽은 항목이 된다.
  let notice = '';
  let cursor = 0;
  // 검색은 서버가 한다 — 전 목록을 받아 거르면 팔레트를 열 때마다 리뷰 수에 비례한
  // 응답을 받고 정작 40건만 쓴다.

  function isOpen() { return !overlay.classList.contains('hidden'); }

  function setCrumb(text) {
    crumbEl.textContent = text || '';
    crumbEl.classList.toggle('hidden', !text);
  }

  /** 항목과 안내를 한 번에 갈아 끼운다 — 둘이 따로 놀면 옛 안내가 새 목록 밑에 남는다. */
  function setRows(newRows, message = '') {
    rows = newRows;
    notice = message;
    cursor = 0;
  }

  function render() {
    cursor = Math.max(0, Math.min(cursor, rows.length - 1));
    const noticeText = notice || (rows.length ? '' : '결과가 없습니다.');
    listEl.innerHTML = rows.map((r, i) => `
          <li>
            <button type="button" class="cmdk-item ${i === cursor ? 'active' : ''}" data-idx="${i}">
              <span class="cmdk-item-label">${escapeHtml(r.label)}</span>
              ${r.meta ? `<span class="cmdk-item-meta">${escapeHtml(r.meta)}</span>` : ''}
            </button>
          </li>`).join('')
      + (noticeText ? `<li class="cmdk-empty">${escapeHtml(noticeText)}</li>` : '');
    listEl.querySelectorAll('.cmdk-item').forEach(b => {
      b.addEventListener('click', () => run(Number(b.dataset.idx)));
    });
    listEl.querySelector('.cmdk-item.active')?.scrollIntoView({ block: 'nearest' });
    // 목록 교체로 포커스가 <body> 로 떨어진다. 노드 제거는 focusout 이 없어 직접 부른다.
    recoverModalFocus(overlay);
  }

  function rootRows(query) {
    const items = [{
      label: '지난 제출 불러오기',
      meta: '기록에서 코드 가져오기',
      run: () => showProblems(),
    }];
    TABS.forEach(([key, label]) => items.push({
      label, meta: '이동', run: () => { close(); activateTab(key); },
    }));
    items.push({
      label: '테마 전환',
      meta: document.documentElement.getAttribute('data-theme') === 'light' ? '다크로' : '라이트로',
      run: () => { close(); document.getElementById('theme-toggle').click(); },
    });
    const q = query.trim().toLowerCase();
    return q ? items.filter(i => i.label.toLowerCase().includes(q)) : items;
  }

  // 세대 토큰 — 목록 조회가 늦게 끝나면 이미 다른 모드로 넘어간 팔레트를 덮는다.
  let _paletteToken = 0;

  const PALETTE_RESULTS = 40;

  function showProblems() {
    mode = 'problems';
    setCrumb('제출 불러오기');
    input.value = '';
    input.placeholder = '문제 번호 · 제목 · 태그로 검색';
    return searchProblems('');
  }

  // 검색어마다 서버에 묻는다. 입력이 멈춘 뒤 한 번만 나가도록 refresh 쪽에서 묶는다.
  async function searchProblems(query) {
    const token = ++_paletteToken;
    setRows([], '불러오는 중...');
    render();
    try {
      const data = await fetchJsonOk(
        `/api/reviews/grouped?${listQuery({ q: query, per_page: PALETTE_RESULTS })}`,
        undefined, '기록 조회 실패');
      if (token !== _paletteToken) return;
      const found = data.problems || [];
      const over = (data.total || 0) - found.length;
      setRows(found.map(p => ({
        label: `${problemLabel(p)}. ${p.title}`,
        meta: `제출 ${p.submission_count || 0}회 · ${localDate(p.last_submitted)}`,
        run: () => showLedger(p),
      })), over > 0 ? `그 외 ${over}건 — 검색어를 좁혀주세요` : '');
      render();
    } catch (e) {
      if (token !== _paletteToken) return;
      setRows([], e.message);
      render();
    }
  }

  async function showLedger(problem) {
    const token = ++_paletteToken;
    mode = 'ledger';
    const platform = problem.platform || 'boj';
    const ref = problem.problem_ref || String(problem.problem_id || '');
    setCrumb(`${problemLabel(problem)}. ${problem.title} — 회차 선택`);
    input.value = '';
    input.placeholder = '회차를 고르세요';
    setRows([], '불러오는 중...');
    render();
    try {
      const data = await fetchJsonOk(
        `/api/reviews/problem/${encodeURIComponent(platform)}/${encodeURIComponent(ref)}`,
        undefined, '기록 조회 실패');
      if (token !== _paletteToken) return;
      const reviews = data.reviews || [];
      const total = reviews.length;
      setRows(reviews.map((r, i) => ({
        label: `#${total - i}  ${localDate(r.created_at)}  ${r.complexity || '-'}`,
        meta: effLabel(r.efficiency),
        run: () => {
          if (!confirmEditorOverwrite()) return;
          close();
          fillReviewForm(r, total - i, total);
        },
      })), reviews.length ? '' : '기록이 없습니다.');
      render();
    } catch (e) {
      if (token !== _paletteToken) return;
      setRows([], e.message);
      render();
    }
  }

  // 문제 검색은 서버로 나가므로 입력이 멈춘 뒤 한 번만 보낸다.
  const searchProblemsDebounced = debounce(query => searchProblems(query), 200);

  function refresh() {
    if (mode === 'root') {
      setRows(rootRows(input.value));
      render();
      return;
    }
    if (mode === 'problems') {
      searchProblemsDebounced(input.value);
      return;
    }
    // ledger 는 회차가 몇 개뿐이라 검색으로 걸러내지 않는다.
    cursor = 0;
    render();
  }

  function run(idx) {
    const row = rows[idx];
    if (row) row.run();
  }

  function open() {
    overlay.classList.remove('hidden');
    mode = 'root';
    setCrumb('');
    input.value = '';
    input.placeholder = '무엇을 할까요?';
    refresh();
    // 포커스 이동·복원은 modal-a11y 에 맡긴다(registerModal 의 initial).
    // 직접 input.focus() 하면 공통 모듈이 '열기 전 포커스' 로 자기 자신을 기억한다.
  }

  function close() {
    // 진행 중인 조회를 무효화한다 — 닫는 사이 도착한 응답이 다시 연 팔레트에 렌더된다.
    _paletteToken++;
    overlay.classList.add('hidden');
  }

  function back() {
    if (mode === 'ledger') { showProblems(); return true; }
    if (mode === 'problems') { _paletteToken++; mode = 'root'; setCrumb(''); input.value = '';
      input.placeholder = '무엇을 할까요?'; refresh(); return true; }
    return false;
  }

  input.addEventListener('input', refresh);

  overlay.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); cursor++; render(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); cursor--; render(); }
    // 버튼에서 올라온 Enter 는 기본 활성화에 맡긴다 — 취소하면 cursor 항목이 대신 실행된다.
    else if (e.key === 'Enter' && e.target === input) { e.preventDefault(); run(cursor); }
    else if (e.key === 'Escape') { e.preventDefault(); if (!back()) close(); }
    else if (e.key === 'Backspace' && !input.value) { if (back()) e.preventDefault(); }
  });

  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  document.getElementById('cmdk-close').addEventListener('click', close);
  document.getElementById('cmdk-open')?.addEventListener('click', open);

  // 자기 Esc 는 "뒤로 한 단계" 의미가 있어 직접 처리한다 — 공통 모듈에는 트랩만 맡긴다.
  registerModal('cmdk', close, { ownsEscape: true, initial: '#cmdk-input' });

  // 핸들러가 metaKey|ctrlKey 를 다 받으므로 표기도 플랫폼에 맞춘다.
  const kbd = document.getElementById('cmdk-kbd');
  if (kbd) {
    const platform = navigator.userAgentData?.platform || navigator.platform || '';
    if (/mac/i.test(platform)) kbd.textContent = '⌘K';
  }

  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      isOpen() ? close() : open();
    }
  });
})();
