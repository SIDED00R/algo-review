/* 탭 전환 — 탭 버튼 클릭 시 탭 섹션 전환만 담당 */

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(s => {
      s.classList.remove('active');
      s.classList.add('hidden');
    });
    btn.classList.add('active');
    const tab = document.getElementById(`tab-${btn.dataset.tab}`);
    tab.classList.remove('hidden');
    tab.classList.add('active');
    if (btn.dataset.tab === 'history') loadHistory();
    if (btn.dataset.tab === 'import') loadImportedHistory();
    if (btn.dataset.tab === 'stats') loadTierChart();

    /* 모바일: 탭 선택 후 nav 닫기 */
    closeNav();
  });
});

/* 햄버거 메뉴 토글 */
const menuToggle = document.getElementById('menu-toggle');
const mainNav = document.getElementById('main-nav');

function closeNav() {
  mainNav?.classList.remove('open');
  if (menuToggle) {
    menuToggle.classList.remove('open');
    menuToggle.setAttribute('aria-expanded', 'false');
  }
}

menuToggle?.addEventListener('click', () => {
  const isOpen = mainNav.classList.toggle('open');
  menuToggle.classList.toggle('open', isOpen);
  menuToggle.setAttribute('aria-expanded', String(isOpen));
});
