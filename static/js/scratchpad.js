// 코드 연습장 — 풀이와 별개로 코드 조각을 입력값과 함께 실행해 보는 창. 상단 헤더와 문제 뷰어 헤더에서 연다.
// 뒤 화면을 막지 않아 문제문·풀이 에디터를 그대로 쓸 수 있고, 머리 줄을 끌어 옮긴다. 닫으면 숨기기만 하므로
// 코드·입력·결과는 새로고침 전까지 남는다. 실행은 예제 실행과 같은 /api/execute 다.
(function () {
  const win = document.getElementById('scratch-window');
  const head = document.getElementById('scratch-head');
  const runBtn = document.getElementById('scratch-run-btn');
  const languageSelect = document.getElementById('scratch-language');
  const stdinInput = document.getElementById('scratch-stdin');
  const resultEl = document.getElementById('scratch-result');
  // 처음 열 때 오른쪽 아래에 둔다. 그 뒤로는 사용자가 옮긴 자리를 유지한다.
  const EDGE_GAP_PX = 16;
  let placed = false;
  let dragOffset = null;

  // 판정은 예제 실행과 같다(problem-modal.js). 비교할 기대 출력이 없어 exit 0 은 '통과'가 아니라 '정상 종료'다.
  const VERDICT_LABELS = { ...SAMPLE_VERDICT_LABELS, pass: '정상 종료' };

  // 창 전체가 뷰포트 안에 남도록 자리를 누른다. 창이 뷰포트보다 크면(max-width/height 가 막는다) 0 이다.
  function moveTo(left, top) {
    const maxLeft = Math.max(0, document.documentElement.clientWidth - win.offsetWidth);
    const maxTop = Math.max(0, document.documentElement.clientHeight - win.offsetHeight);
    win.style.left = `${Math.min(Math.max(0, left), maxLeft)}px`;
    win.style.top = `${Math.min(Math.max(0, top), maxTop)}px`;
  }

  function keepInView() {
    if (win.classList.contains('hidden')) return;
    const rect = win.getBoundingClientRect();
    moveTo(rect.left, rect.top);
  }

  function openScratchWindow() {
    if (!win.classList.contains('hidden')) {
      window.cmEditors['scratch-code']?.focus();
      return;
    }
    win.classList.remove('hidden');
    if (placed) {
      keepInView();
    } else {
      placed = true;
      moveTo(document.documentElement.clientWidth - win.offsetWidth - EDGE_GAP_PX,
             document.documentElement.clientHeight - win.offsetHeight - EDGE_GAP_PX);
    }
  }

  function closeScratchWindow() {
    win.classList.add('hidden');
  }

  function renderResult(result) {
    // 출력 비교 없이 종료 상태만 가른다 — matched 를 참으로 준다.
    const verdict = sampleVerdict(result, true);
    const exitHtml = result.exit_code !== 0 ? `<span class="tc-exit">exit ${result.exit_code}</span>` : '';
    const stdout = result.stdout || '';
    const stdoutHtml = stdout
      ? `<pre class="code-block">${escapeHtml(stdout)}</pre>`
      : '<p class="hint">출력 없음</p>';
    const stderrHtml = result.stderr ? `
      <span class="label">오류 출력 (stderr)</span>
      <pre class="code-block">${escapeHtml(result.stderr)}</pre>` : '';
    return `
      <div class="test-case ${verdict === 'pass' ? 'pass' : 'fail'}" data-verdict="${verdict}">
        <span class="tc-badge">${VERDICT_LABELS[verdict]}</span>
        <span class="tc-time">${result.time_ms}ms</span>${exitHtml}
      </div>
      <span class="label">출력 (stdout)</span>
      ${stdoutHtml}${stderrHtml}`;
  }

  // 실행 중에는 버튼이 막혀 있어 한 번에 하나만 돈다. 창을 닫아도 노드는 남으므로 늦은 응답이 그대로 그려진다.
  async function runScratch() {
    const code = window.getEditorValue('scratch-code');
    if (!code.trim()) {
      resultEl.innerHTML = '<div class="alert alert-info">코드를 먼저 작성해주세요.</div>';
      return;
    }
    // 포커스를 가진 버튼을 막으면 포커스가 body 로 떨어진다 — 먼저 에디터로 옮긴다.
    if (document.activeElement === runBtn) window.cmEditors['scratch-code']?.focus();
    runBtn.disabled = true;
    runBtn.textContent = '실행 중...';
    resultEl.innerHTML = '<div class="test-case pending"><span class="spinner spinner-sm"></span> 실행 중...</div>';
    try {
      const result = await fetchJsonOk('/api/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language: languageSelect.value, stdin: stdinInput.value, timeout_sec: 5 }),
      }, '실행 실패');
      resultEl.innerHTML = renderResult(result);
    } catch (e) {
      resultEl.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = '실행';
    }
  }

  // ── 끌어서 옮기기 ── 포인터 캡처라 커서가 창 밖으로 빨리 나가도 놓치지 않는다.
  head.addEventListener('pointerdown', e => {
    if (e.button !== 0 || e.target.closest('button, select')) return;
    const rect = win.getBoundingClientRect();
    dragOffset = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    head.setPointerCapture(e.pointerId);
  });
  head.addEventListener('pointermove', e => {
    if (!dragOffset || !head.hasPointerCapture(e.pointerId)) return;
    moveTo(e.clientX - dragOffset.x, e.clientY - dragOffset.y);
  });
  for (const type of ['pointerup', 'pointercancel']) {
    head.addEventListener(type, () => { dragOffset = null; });
  }

  // 창이 보이게 되거나(숨김 0×0 → 실제 크기) 사용자가 크기를 바꾸면 에디터를 다시 잰다 — 숨긴 채 만든
  // CodeMirror 는 크기를 0 으로 잰다. 창이나 뷰포트가 바뀌면 화면 밖으로 나간 부분을 되돌린다.
  new ResizeObserver(() => {
    if (win.classList.contains('hidden')) return;
    window.cmEditors['scratch-code']?.refresh();
    keepInView();
  }).observe(win);
  window.addEventListener('resize', keepInView);

  document.getElementById('scratch-open-btn').addEventListener('click', openScratchWindow);
  document.getElementById('pm-scratch-btn').addEventListener('click', openScratchWindow);
  document.getElementById('scratch-close-btn').addEventListener('click', closeScratchWindow);
  runBtn.addEventListener('click', runScratch);

  // 포커스 트랩·초기 포커스·닫을 때 복원은 공통 모듈이 맡는다. 에디터가 든 창이라 Esc 로 닫지 않는다(닫기는 ✕ 버튼).
  registerModal('scratch-window', closeScratchWindow,
                { initial: '#scratch-code textarea', escapeCloses: false });
})();
