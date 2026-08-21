// 탭 전환은 여기 한 곳에만 둔다 — 예전에는 problem-modal.js 가 같은 클래스 토글을
// 따로 갖고 있어서 탭별 lazy loader 와 모바일 메뉴 닫기를 건너뛰었다.
function activateTab(name) {
  const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
  const tab = document.getElementById(`tab-${name}`);
  if (!btn || !tab) return;

  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
  });
  document.querySelectorAll('.tab-content').forEach(s => {
    s.classList.remove('active');
    s.classList.add('hidden');
  });

  btn.classList.add('active');
  btn.setAttribute('aria-selected', 'true');
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
