// 탭 전환은 여기 한 곳에만 둔다 — 다른 모듈이 같은 클래스 토글을
// 따로 가지면 탭별 lazy loader 와 모바일 메뉴 닫기를 건너뛴다.
function activateTab(name) {
  const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
  const tab = document.getElementById(`tab-${name}`);
  if (!btn || !tab) return;

  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
    // roving tabindex — 활성 탭만 탭 순서에 둔다. ARIA tabs 패턴에서 Tab 은 탭 목록을
    // 통과하고 목록 안 이동은 화살표 키가 담당한다.
    b.setAttribute('tabindex', '-1');
  });
  document.querySelectorAll('.tab-content').forEach(s => {
    s.classList.remove('active');
    s.classList.add('hidden');
  });

  btn.classList.add('active');
  btn.setAttribute('aria-selected', 'true');
  btn.setAttribute('tabindex', '0');
  tab.classList.remove('hidden');
  tab.classList.add('active');

  if (name === 'history') loadHistory();
  if (name === 'import') loadImportedHistory();
  if (name === 'stats') loadTierChart();
  if (name === 'themes') loadThemes();

  closeNav();
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => activateTab(btn.dataset.tab));
});

// role="tablist" 를 선언했으면 화살표 키 이동이 있어야 한다 — 보조기술 사용자는 그것을
// 기대한다 — 선언만 있고 동작이 없으면 없는 것보다 나쁘다.
document.getElementById('main-nav')?.addEventListener('keydown', e => {
  const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
  const tabs = [...document.querySelectorAll('.tab-btn')];
  const here = tabs.indexOf(document.activeElement);
  if (here === -1) return;

  let next = null;
  if (e.key in keys) next = (here + keys[e.key] + tabs.length) % tabs.length;
  else if (e.key === 'Home') next = 0;
  else if (e.key === 'End') next = tabs.length - 1;
  if (next === null) return;

  e.preventDefault();
  activateTab(tabs[next].dataset.tab);
  tabs[next].focus();
});

const menuToggle = document.getElementById('menu-toggle');
const mainNav = document.getElementById('main-nav');

function closeNav() {
  mainNav.classList.remove('open');
  menuToggle.classList.remove('open');
  menuToggle.setAttribute('aria-expanded', 'false');
}

menuToggle.addEventListener('click', () => {
  const isOpen = mainNav.classList.toggle('open');
  menuToggle.classList.toggle('open', isOpen);
  menuToggle.setAttribute('aria-expanded', String(isOpen));
});
