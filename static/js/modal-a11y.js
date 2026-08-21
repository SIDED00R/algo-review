// 모달 접근성 — Esc 닫기 · 포커스 트랩 · 초기 포커스 · 복원을 한 곳에 둔다.
// 예전에는 #cmdk 만 초기 포커스·복원을 갖고, #problem-modal 은 Esc 만, #review-modal 은
// 둘 다 없었다. 규약을 세 곳에 복제하면 새 모달을 추가할 때 또 빠진다.
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

    // 포커스가 모달 밖(대개 <body>)으로 새면 되돌린다. 진행 중 버튼을 disabled 로
    // 만들거나(setLoading) 목록을 innerHTML 로 교체하면 브라우저가 포커스를 <body> 로
    // 옮기는데, 그 순간 keydown 리스너가 이 root 에 걸려 있어 **Esc 로 모달을 닫을 수
    // 없고 Tab 트랩도 무효**가 된다. 10~20초짜리 작업에서 실제로 발생한다.
    root.addEventListener('focusout', e => {
        if (root.classList.contains('hidden')) return;
        // relatedTarget 이 null 이면 포커스가 문서 밖·body 로 간 것이다.
        if (e.relatedTarget && root.contains(e.relatedTarget)) return;
        // 마이크로태스크로 미룬다 — focusout 시점에는 새 포커스가 아직 확정되지 않는다.
        queueMicrotask(() => {
          if (root.classList.contains('hidden')) return;
          if (root.contains(document.activeElement)) return;
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
