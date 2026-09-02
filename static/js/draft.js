// 에디터 임시 저장 — 작성 중인 코드를 서버(`/api/drafts/{key}`)에 자동 저장하고 다시 열 때 복원한다.
// 키 하나가 에디터 자리 하나다: 메인 리뷰 탭은 `main`, 문제 뷰어는 문제마다 `codeforces:{ref}`.
(function () {
  // 입력이 멎고 이만큼 뒤에 저장한다.
  const DEBOUNCE_MS = 1500;
  // 첫 변경 후 이만큼 지나면 디바운스를 더 밀지 않고 저장한다.
  const MAX_WAIT_MS = 5000;

  // 에디터마다 언어 select 가 다르다. 언어도 함께 저장해 복원 때 되돌린다.
  const LANG_SELECT = {
    'code-input': 'code-language',
    'pm-code': 'pm-language',
  };

  // editorId → 바인딩 상태. key 가 null 이면 저장하지 않는다(바인딩 전·해제 후).
  //   saved   : 서버에 있다고 아는 코드. 같으면 저장하지 않는다.
  //   loaded  : 저장본을 읽었는지. 읽었을 때만 자동 저장한다.
  //   token   : 자리 세대. 늦게 온 응답을 버리는 데 쓴다.
  const _drafts = {};

  function draftState(editorId) {
    if (!_drafts[editorId]) {
      _drafts[editorId] = { key: null, token: 0, saved: '', loaded: false,
                            timer: null, dirtySince: 0 };
    }
    return _drafts[editorId];
  }

  function setDraftStatus(editorId, text, isError) {
    const el = document.getElementById(`${editorId}-draft-status`);
    if (!el) return;
    el.textContent = text;
    el.classList.toggle('hint-bad', !!isError);
  }

  /** 저장 시각을 보는 사람의 시간대 `HH:MM` 으로. 저장값은 UTC 다. */
  function draftTimeLabel(updatedAt) {
    const d = parseStoredTime(updatedAt);
    if (!d) return '';
    const pad = n => String(n).padStart(2, '0');
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function draftLanguage(editorId) {
    const sel = document.getElementById(LANG_SELECT[editorId]);
    return (sel && sel.value) || '';
  }

  /** 복원한 언어를 select 에 되돌린다. */
  function applyDraftLanguage(editorId, language) {
    const sel = document.getElementById(LANG_SELECT[editorId]);
    if (!sel || !language) return;
    // select 에 없는 값을 대입하면 조용히 실패해 selectedIndex 가 -1 이 된다.
    if (![...sel.options].some(o => o.value === language)) return;
    sel.value = language;
    // 프로그램으로 바꾼 값은 change 를 발화시키지 않는다 — 에디터 모드 전환이 그 이벤트에 걸려 있다.
    sel.dispatchEvent(new Event('change'));
  }

  /**
   * 지금 내용을 임시 저장한다.
   * @param {string} editorId
   * @param {boolean} manual  '임시 저장' 버튼 경로. 자동 저장이 꺼진 자리도 저장한다.
   */
  async function saveDraft(editorId, manual) {
    const st = draftState(editorId);
    clearTimeout(st.timer);
    st.dirtySince = 0;
    if (!st.key) return;
    // 저장본을 읽지 못한 자리는 자동으로 쓰지 않는다.
    if (!st.loaded && !manual) return;
    const code = window.getEditorValue(editorId);
    if (code === st.saved && !manual) return;
    const key = st.key;
    const token = st.token;
    setDraftStatus(editorId, '임시 저장 중...');
    try {
      const data = await fetchJsonOk(`/api/drafts/${encodeURIComponent(key)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language: draftLanguage(editorId) }),
      }, '임시 저장 실패');
      if (token !== st.token) return;   // 그 사이 다른 자리로 옮겼다
      st.saved = code;
      st.loaded = true;
      // updated_at 이 없으면 서버가 빈 코드를 받아 저장본을 지운 것이다.
      setDraftStatus(editorId, data.updated_at
        ? `임시 저장됨 ${draftTimeLabel(data.updated_at)}`
        : '저장할 코드가 없어 임시 저장본을 지웠습니다');
    } catch (e) {
      if (token !== st.token) return;
      setDraftStatus(editorId, `임시 저장 실패 — ${e.message}`, true);
    }
  }

  function scheduleDraftSave(editorId) {
    const st = draftState(editorId);
    if (!st.key) return;
    if (!st.dirtySince) st.dirtySince = Date.now();
    clearTimeout(st.timer);
    if (Date.now() - st.dirtySince >= MAX_WAIT_MS) {
      saveDraft(editorId, false);
      return;
    }
    st.timer = setTimeout(() => saveDraft(editorId, false), DEBOUNCE_MS);
  }

  /** 에디터를 임시 저장 키에 붙이고, 저장본이 있으면 복원한다. */
  async function bindDraft(editorId, key) {
    // 에디터가 없으면(CodeMirror 미로드) 붙지 않는다.
    if (!window.cmEditors?.[editorId]) return;
    const st = draftState(editorId);
    clearTimeout(st.timer);
    const token = ++st.token;
    st.key = key;
    st.saved = '';
    st.loaded = false;
    st.dirtySince = 0;
    setDraftStatus(editorId, '임시 저장본 확인 중...');

    let data;
    try {
      data = await fetchJsonOk(`/api/drafts/${encodeURIComponent(key)}`, undefined,
                               '임시 저장본 조회 실패');
    } catch (e) {
      if (token !== st.token) return;
      // loaded 를 세우지 않는다 — 이 자리는 '임시 저장' 버튼으로만 저장된다.
      setDraftStatus(editorId, `임시 저장본을 불러오지 못했습니다 (자동 저장 꺼짐) — ${e.message}`, true);
      return;
    }
    if (token !== st.token) return;

    st.loaded = true;
    st.saved = data.code || '';
    // 에디터에 이미 내용이 있으면 덮지 않는다.
    if (data.code && !window.getEditorValue(editorId).trim()) {
      applyDraftLanguage(editorId, data.language);
      window.setEditorValue(editorId, data.code);
      setDraftStatus(editorId, `임시 저장본을 불러왔습니다 (${draftTimeLabel(data.updated_at)})`);
      return;
    }
    setDraftStatus(editorId, data.updated_at ? `임시 저장됨 ${draftTimeLabel(data.updated_at)}` : '');
  }

  /** 자리를 떠난다 — 대기 중인 변경을 보내고 키를 뗀다. 응답을 기다리지 않는다. */
  function unbindDraft(editorId) {
    const st = draftState(editorId);
    if (!st.key) return;
    saveDraft(editorId, false);
    st.key = null;
    st.token++;
    setDraftStatus(editorId, '');
  }

  window.bindDraft = bindDraft;
  window.unbindDraft = unbindDraft;

  Object.keys(LANG_SELECT).forEach(editorId => {
    const cm = window.cmEditors[editorId];
    if (!cm) return;
    // CodeMirror 는 setValue 도 change 로 알린다.
    cm.on('change', () => scheduleDraftSave(editorId));
    document.getElementById(LANG_SELECT[editorId])
      ?.addEventListener('change', () => scheduleDraftSave(editorId));
    document.getElementById(`${editorId}-draft-btn`)
      ?.addEventListener('click', () => saveDraft(editorId, true));
  });

  // 메인 리뷰 탭 에디터는 자리가 하나뿐이라 여기서 붙인다.
  // 문제 뷰어는 문제마다 키가 달라 problem-modal.js 가 열 때 붙인다.
  bindDraft('code-input', 'main');
})();
