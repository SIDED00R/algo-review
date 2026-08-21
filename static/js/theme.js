const themeBtn = document.getElementById('theme-toggle');
const themeIconUse = themeBtn.querySelector('use');

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  themeIconUse.setAttribute('href', theme === 'light' ? '#i-sun' : '#i-moon');
  themeBtn.setAttribute('aria-pressed', String(theme === 'light'));
}

// data-theme 은 index.html <head> 인라인 스크립트가 페인트 전에 이미 확정한다
// (그러지 않으면 라이트 모드 사용자가 매 로드마다 다크 화면을 한 프레임 본다).
// 여기서는 그 값에 아이콘·aria 만 맞춘다.
applyTheme(document.documentElement.getAttribute('data-theme') || 'dark');

themeBtn.addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  applyTheme(next);
  try { localStorage.setItem('theme', next); } catch (e) { /* 저장소 차단 */ }
});
