// 모달 접근성 — Esc 닫기 · 포커스 트랩 · 초기 포커스 · 복원을 한 곳에 둔다.
// 모달마다 복제하면 새 모달을 추가할 때 일부가 빠진다.
(function () {
  const FOCUSABLE = [
    'a[href]', 'button:not([disabled])', 'input:not([disabled])',
    'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
  ].join(',');

  /** 컨테이너 안에서 실제로 보이는 포커스 가능 요소. */
  function focusables(root) {
    return [...root.querySelectorAll(FOCUSABLE)].filter(el =>
      !el.closest('.hidden') && el.offsetParent !== null);
  }

  const restore = new WeakMap();

  /** 모달이 열릴 때 — 여는 쪽의 포커스를 기억하고 첫 컨트롤로 옮긴다. */
  function onOpen(root, initialSelector) {
    restore.set(root, document.activeElement);
    const target = (initialSelector && root.querySelector(initialSelector)) || focusables(root)[0];
    if (target) target.focus();
  }

  /** 포커스가 <body> 로 떨어졌으면 모달 안으로 되돌린다. 다른 요소로 옮겨 갔으면 둔다.
   *  innerHTML 교체처럼 focusout 이 발화하지 않는 경로에서 직접 부른다. */
  function recoverFocus(root) {
    if (!root || root.classList.contains('hidden')) return;
    // onOpen 전이면(장부가 비어 있다) 아무것도 하지 않는다 — MutationObserver 가
    // 마이크로태스크라, 그 사이 포커스를 옮기면 onOpen 이 모달 안의 요소를 기억한다.
    if (!restore.has(root)) return;
    if (document.activeElement && document.activeElement !== document.body) return;
    (focusables(root)[0] || root).focus();
  }

  /** 모달이 닫힐 때 — 열기 전 위치로 되돌린다. */
  function onClose(root) {
    const prev = restore.get(root);
    restore.delete(root);
    if (prev && document.contains(prev)) prev.focus();
  }

  /**
   * 모달 하나를 등록한다.
   * @param {string} id            모달 루트 엘리먼트 id
   * @param {function} close       닫기 함수(각 모달이 자기 정리를 한다)
   * @param {object} [opts]
   * @param {string} [opts.initial]  열릴 때 포커스할 셀렉터
   * @param {boolean} [opts.ownsEscape]  모달이 이미 Esc 를 처리하면 true (중복 방지)
   */
  function registerModal(id, close, opts = {}) {
    const root = document.getElementById(id);
    if (!root) return;
    // tabindex 가 없으면 root.focus() 가 조용히 무효다 — 안에 포커스 가능한 요소가
    // 하나도 없을 때 회수에 실패한다.
    root.tabIndex = -1;

    root.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !opts.ownsEscape) {
        e.preventDefault();
        e.stopPropagation();   // 겹쳐 열린 상위 모달까지 함께 닫히지 않게 한다
        close();
        return;
      }
      if (e.key !== 'Tab') return;

      const items = focusables(root);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });

    // 포커스가 아무 데도 가지 않은 경우에만 모달 안으로 되돌린다. Esc·Tab 트랩 리스너가
    // root 에 걸려 있어 포커스가 <body> 에 있으면 이 모달에 도달하지 않는다.
    // 노드가 DOM 에서 제거되는 경우는 focusout 이 없어 잡지 못한다 — 목록을 innerHTML 로
    // 교체하는 쪽이 재렌더 직후 recoverFocus 를 부른다.
    root.addEventListener('focusout', e => {
      if (root.classList.contains('hidden')) return;
      if (e.relatedTarget) return;   // 갈 곳이 있는 이동이다
      // focusout 시점에는 새 포커스가 아직 확정되지 않는다 — 마이크로태스크로 미룬다.
      queueMicrotask(() => recoverFocus(root));
    });

    // 열림/닫힘은 .hidden 토글로 표현된다 — 그 변화를 감시해 포커스를 다룬다.
    let wasOpen = !root.classList.contains('hidden');
    // 등록 시점에 이미 열려 있으면 감시자는 아무 변화도 보지 못한다. 그러면 장부가 비어
    // recoverFocus 가 영구 no-op 이 되므로, 여기서 한 번 열림 처리를 해 둔다.
    if (wasOpen) onOpen(root, opts.initial);
    new MutationObserver(() => {
      const isOpen = !root.classList.contains('hidden');
      if (isOpen === wasOpen) return;
      wasOpen = isOpen;
      if (isOpen) onOpen(root, opts.initial);
      else onClose(root);
    }).observe(root, { attributes: true, attributeFilter: ['class'] });
  }

  window.registerModal = registerModal;
  window.recoverModalFocus = recoverFocus;
})();
