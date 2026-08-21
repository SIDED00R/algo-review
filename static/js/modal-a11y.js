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
    // 마지막 수단으로 포커스를 받을 수 있어야 한다 — tabindex 가 없으면 root.focus() 가
    // 조용히 무효라서, 안에 포커스 가능한 요소가 하나도 없을 때 회수에 실패한다
    // (진행 중 버튼이 disabled 되면 `button:not([disabled])` 에서 빠져 실제로 그렇게 된다).
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

    // 포커스가 **아무 데도 가지 않은** 경우에만 모달 안으로 되돌린다.
    // 이 모달의 keydown 리스너는 root 에 걸려 있으므로, 포커스가 <body> 에 있으면
    // Esc 도 Tab 트랩도 이 모달에 도달하지 않는다. 포커스를 가진 요소가 disabled 되거나
    // (setLoading) DOM 에서 사라지면 브라우저가 포커스를 <body> 로 옮긴다.
    //
    // 다른 요소로 이동한 포커스는 건드리지 않는다. 위에 다른 모달이 열려 자기 입력에
    // 포커스를 주면, 두 모달이 서로 회수하며 microtask 루프에 빠져 탭이 정지한다.
    root.addEventListener('focusout', e => {
      if (root.classList.contains('hidden')) return;
      if (e.relatedTarget) return;   // 갈 곳이 있는 이동이다
      // focusout 시점에는 새 포커스가 아직 확정되지 않는다 — 마이크로태스크로 미룬다.
      queueMicrotask(() => {
        if (root.classList.contains('hidden')) return;
        if (document.activeElement && document.activeElement !== document.body) return;
        (focusables(root)[0] || root).focus();
      });
    });

    // 열림/닫힘은 .hidden 토글로 표현된다 — 그 변화를 감시해 포커스를 다룬다.
    let wasOpen = !root.classList.contains('hidden');
    new MutationObserver(() => {
      const isOpen = !root.classList.contains('hidden');
      if (isOpen === wasOpen) return;
      wasOpen = isOpen;
      if (isOpen) onOpen(root, opts.initial);
      else onClose(root);
    }).observe(root, { attributes: true, attributeFilter: ['class'] });
  }

  window.registerModal = registerModal;
})();
