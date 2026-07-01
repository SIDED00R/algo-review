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
    if (btn.dataset.tab === 'themes') loadThemes();

    closeNav();
  });
});

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
