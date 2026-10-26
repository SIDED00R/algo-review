// 분할 손잡이 — 두 패널 사이의 role="separator" 요소를 끌거나(포인터 캡처) 화살표 키로 움직여 첫 패널의
// 비율을 컨테이너의 CSS 변수(`NN%`)에 쓴다. 비율을 % 로 두므로 창 크기가 바뀌어도 레이아웃이 따라오고,
// 저장값도 화면 크기에 묶이지 않는다. 저장은 themes.js 의 _lsGet/_lsSet(전역)을 호출 시점에 쓴다.
// 최소 크기는 CSS 가 실제로 지키고(clamp() 의 양 끝 — 상하 분할의 아래 패널은 낮은 창에서 min-height 가 지킨다),
// 여기서는 같은 수치로 aria-valuenow·저장값을 맞춘다(컨테이너가 첫 패널 최소보다 작으면 100 으로 막는다).
(function () {
  const KEY_STEP_PCT = 2;
  const PAGE_STEP_PCT = 10;

  function readSaved(key) {
    const value = _lsGet(key, Infinity);
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  }

  /**
   * @param {object} o
   * @param {HTMLElement} o.handle        role="separator", tabindex=0
   * @param {HTMLElement} o.container     비율의 기준(content-box)이자 CSS 변수를 받는 요소
   * @param {'vertical'|'horizontal'} o.orientation  vertical = 좌우 분할(손잡이가 세로 선)
   * @param {string} o.cssVar             예: '--pm-left-w'
   * @param {string} o.storageKey         예: 'viewer:split:v1:left'
   * @param {number} o.defaultPct
   * @param {number} o.minPx              첫 패널 최소 px — CSS clamp() 의 첫 인자와 같다
   * @param {number} o.minRemainingPx     둘째 패널 최소 px(손잡이·gap 포함) — clamp() 의 calc 와 같다
   * @param {function} [o.onResize]       비율을 적용한 뒤(드래그 중 프레임당 1회)
   * @returns {{get: function(): number, set: function(number): void}|null}
   */
  function attachPaneSplitter(o) {
    const { handle, container, orientation, cssVar, storageKey, defaultPct, minPx, minRemainingPx, onResize } = o;
    if (!handle || !container) return null;
    const vertical = orientation === 'vertical';
    let pct = defaultPct;
    let frame = 0;
    let pending = null;
    // 잡은 순간 포인터와 분할선 사이 거리. 빼지 않으면 첫 움직임에 분할선이 포인터 자리로 튄다
    // (손잡이 폭·gap 만큼). 비율은 CSS clamp 와 같은 범위로 먼저 눌러 화면의 실제 위치와 맞춘다.
    let grabOffset = 0;

    // 컨테이너 content-box 의 축 방향 시작·길이. CSS 의 % 도 같은 상자를 기준으로 풀린다.
    function metrics() {
      const rect = container.getBoundingClientRect();
      const cs = getComputedStyle(container);
      if (vertical) {
        const padStart = parseFloat(cs.paddingLeft) || 0;
        const padEnd = parseFloat(cs.paddingRight) || 0;
        return { start: rect.left + padStart, size: rect.width - padStart - padEnd };
      }
      const padStart = parseFloat(cs.paddingTop) || 0;
      const padEnd = parseFloat(cs.paddingBottom) || 0;
      return { start: rect.top + padStart, size: rect.height - padStart - padEnd };
    }

    function clampPct(value, size) {
      if (!(size > 0)) return value;
      const low = minPx / size * 100;
      const high = 100 - minRemainingPx / size * 100;
      // 두 최소 합이 컨테이너보다 크면(낮은 창) 범위가 비어 첫 패널 최소를 택한다 — 100% 는 넘기지 않는다
      // (aria-valuemax 가 100 이다).
      if (high <= low) return Math.min(low, 100);
      return Math.min(high, Math.max(low, value));
    }

    function clamped(value) {
      return clampPct(value, metrics().size);
    }

    function apply(value, persist) {
      pct = value;
      container.style.setProperty(cssVar, pct.toFixed(2) + '%');
      handle.setAttribute('aria-valuenow', String(Math.round(pct)));
      if (persist) _lsSet(storageKey, pct);
      if (onResize) onResize();
    }

    handle.setAttribute('aria-valuemin', '0');
    handle.setAttribute('aria-valuemax', '100');
    // 모달이 hidden 이어도 CSS 변수는 먹는다 — 첫 열림부터 저장 비율이 적용된다.
    apply(readSaved(storageKey) ?? defaultPct, false);

    // pointerup 뒤 lostpointercapture 가 한 번 더 오므로 is-dragging 으로 중복을 막는다.
    function end() {
      if (!handle.classList.contains('is-dragging')) return;
      handle.classList.remove('is-dragging');
      container.classList.remove('is-resizing');
      if (frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
      if (pending !== null) {
        apply(pending, false);
        pending = null;
      }
      apply(pct, true);
    }

    handle.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      // 텍스트 선택 시작과 호환 마우스 이벤트를 막는다 — 대신 포커스는 직접 준다.
      e.preventDefault();
      const m = metrics();
      const pos = vertical ? e.clientX : e.clientY;
      grabOffset = pos - (m.start + clampPct(pct, m.size) / 100 * m.size);
      handle.setPointerCapture(e.pointerId);
      handle.classList.add('is-dragging');
      container.classList.add('is-resizing');
      handle.focus();
    });
    handle.addEventListener('pointermove', e => {
      if (!handle.hasPointerCapture(e.pointerId)) return;
      const m = metrics();
      const pos = vertical ? e.clientX : e.clientY;
      pending = clampPct((pos - grabOffset - m.start) / m.size * 100, m.size);
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          if (pending !== null) {
            apply(pending, false);
            pending = null;
          }
        });
      }
    });
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
    handle.addEventListener('lostpointercapture', end);

    handle.addEventListener('keydown', e => {
      const decrease = vertical ? 'ArrowLeft' : 'ArrowUp';
      const increase = vertical ? 'ArrowRight' : 'ArrowDown';
      let next = null;
      if (e.key === decrease) next = pct - KEY_STEP_PCT;
      else if (e.key === increase) next = pct + KEY_STEP_PCT;
      else if (e.key === 'PageUp') next = pct - PAGE_STEP_PCT;
      else if (e.key === 'PageDown') next = pct + PAGE_STEP_PCT;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = 100;
      if (next === null) return;
      e.preventDefault();
      apply(clamped(next), true);
    });
    handle.addEventListener('dblclick', () => apply(clamped(defaultPct), true));

    return { get: () => pct, set: value => apply(clamped(value), true) };
  }

  window.attachPaneSplitter = attachPaneSplitter;
})();
