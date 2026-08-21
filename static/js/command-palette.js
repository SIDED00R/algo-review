// ⌘K 팔레트 — 탭 이동과 '지난 제출 불러오기' 를 한 곳에서 한다.
// 메인 탭의 불러오기 버튼은 지금 입력된 문제의 최신 회차만 집어 온다. 문제 번호를
// 기억하지 못하거나 과거 회차를 고르려면 이 경로를 쓴다.
//
// 내부 이름이 많아 IIFE 로 감싼다 — 스크립트가 전역 렉시컬 스코프를 공유해서
// 최상위 const 이름이 겹치면 전체 스크립트가 SyntaxError 로 죽는다(editor.js 와 같은 이유).
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
  let rows = [];            // 현재 화면에 보이는 항목 [{label, meta, run}]
  let cursor = 0;
  let problems = null;      // /api/reviews/grouped 캐시 (팔레트를 여는 동안만)

  function isOpen() { return !overlay.classList.contains('hidden'); }

  function setCrumb(text) {
    crumbEl.textContent = text || '';
    crumbEl.classList.toggle('hidden', !text);
  }

  function render() {
    cursor = Math.max(0, Math.min(cursor, rows.length - 1));
    listEl.innerHTML = rows.length
      ? rows.map((r, i) => `
          <li>
            <button type="button" class="cmdk-item ${i === cursor ? 'active' : ''}" data-idx="${i}">
              <span class="cmdk-item-label">${escapeHtml(r.label)}</span>
              ${r.meta ? `<span class="cmdk-item-meta">${escapeHtml(r.meta)}</span>` : ''}
            </button>
          </li>`).join('')
      : '<li class="cmdk-empty">결과가 없습니다.</li>';
    listEl.querySelectorAll('.cmdk-item').forEach(b => {
      b.addEventListener('click', () => run(Number(b.dataset.idx)));
    });
    listEl.querySelector('.cmdk-item.active')?.scrollIntoView({ block: 'nearest' });
    // 목록을 통째로 교체하므로 항목 버튼에 있던 포커스가 <body> 로 떨어진다.
    // keydown 리스너가 overlay 에 걸려 있어 그 상태로는 ↑↓·Enter·Esc 가 무반응이 된다.
    // 포커스가 실제로 사라진 경우에만 되돌린다 — 다른 요소로 옮겨간 포커스를 뺏으면
    // modal-a11y 가 기억하는 "열기 전 포커스" 가 #cmdk-input 자신이 되어 복원이 깨진다.
    if (!overlay.classList.contains('hidden')
        && (!document.activeElement || document.activeElement === document.body)) {
      input.focus();
    }
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

  async function showProblems() {
    const token = ++_paletteToken;
    mode = 'problems';
    setCrumb('제출 불러오기');
    input.value = '';
    input.placeholder = '문제 번호 · 제목 · 태그로 검색';
    rows = [{ label: '불러오는 중...', meta: '', run: () => {} }];
    render();
    try {
      if (!problems) {
        const data = await fetchJsonOk('/api/reviews/grouped', undefined, '기록 조회 실패');
        problems = data.problems || [];
      }
      if (token !== _paletteToken) return;
      refresh();
    } catch (e) {
      if (token !== _paletteToken) return;
      rows = [{ label: e.message, meta: '', run: () => {} }];
      render();
    }
  }

  function problemRows(query) {
    return (problems || [])
      .filter(p => matchesProblemQuery(p, query))
      .slice(0, 40)
      .map(p => ({
        label: `${problemLabel(p)}. ${p.title}`,
        meta: `제출 ${p.submission_count || 0}회 · ${String(p.last_submitted || '').slice(0, 10)}`,
        run: () => showLedger(p),
      }));
  }

  async function showLedger(problem) {
    const token = ++_paletteToken;
    mode = 'ledger';
    const platform = problem.platform || 'boj';
    const ref = problem.problem_ref || String(problem.problem_id || '');
    setCrumb(`${problemLabel(problem)}. ${problem.title} — 회차 선택`);
    input.value = '';
    input.placeholder = '회차를 고르세요';
    rows = [{ label: '불러오는 중...', meta: '', run: () => {} }];
    render();
    try {
      const data = await fetchJsonOk(
        `/api/reviews/problem/${encodeURIComponent(platform)}/${encodeURIComponent(ref)}`,
        undefined, '기록 조회 실패');
      if (token !== _paletteToken) return;
      const reviews = data.reviews || [];
      const total = reviews.length;
      rows = reviews.map((r, i) => ({
        label: `#${total - i}  ${String(r.created_at || '').slice(0, 10)}  ${r.complexity || '-'}`,
        meta: effLabel(r.efficiency),
        run: () => {
          if (!confirmEditorOverwrite()) return;
          close();
          fillReviewForm(r, total - i, total);
        },
      }));
      if (!rows.length) rows = [{ label: '기록이 없습니다.', meta: '', run: () => {} }];
      render();
    } catch (e) {
      if (token !== _paletteToken) return;
      rows = [{ label: e.message, meta: '', run: () => {} }];
      render();
    }
  }

  function refresh() {
    if (mode === 'root') rows = rootRows(input.value);
    else if (mode === 'problems') rows = problemRows(input.value);
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
    problems = null;   // 팔레트를 열 때마다 최신 목록을 받는다
    setCrumb('');
    input.value = '';
    input.placeholder = '무엇을 할까요?';
    refresh();
    // 포커스 이동·복원은 modal-a11y 에 맡긴다(아래 registerModal 의 initial).
    // 여기서 직접 input.focus() 를 하면 공통 모듈이 "열기 전 포커스" 로 #cmdk-input
    // 자신을 기억해, 닫을 때 숨겨진 입력으로 되돌리려 하는 장부가 하나 더 생긴다.
  }

  function close() {
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
    // 버튼에서 올라온 Enter 는 그 버튼의 기본 활성화에 맡긴다 — 여기서 취소하면
    // 포커스한 항목 대신 cursor 항목이 실행되고, 닫기 버튼은 Enter 로 눌리지 않는다.
    else if (e.key === 'Enter' && e.target === input) { e.preventDefault(); run(cursor); }
    else if (e.key === 'Escape') { e.preventDefault(); if (!back()) close(); }
    else if (e.key === 'Backspace' && !input.value) { if (back()) e.preventDefault(); }
  });

  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  document.getElementById('cmdk-close').addEventListener('click', close);
  document.getElementById('cmdk-open')?.addEventListener('click', open);

  // 자기 Esc 는 "뒤로 한 단계" 의미가 있어 직접 처리한다 — 공통 모듈에는 트랩만 맡긴다.
  registerModal('cmdk', close, { ownsEscape: true, initial: '#cmdk-input' });

  // 표기를 플랫폼에 맞춘다 — 핸들러는 metaKey|ctrlKey 를 다 받는데 UI 는 macOS 글리프만
  // 보여줬다. 백준·CF 사용자 다수가 Windows 다.
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
