// 테마별 문제 탭 (Codeforces) — 최초 진입 시 한 번만 로드한다.
let _themesLoaded = false;

async function loadThemes() {
  if (_themesLoaded) return;
  const result = document.getElementById('themes-result');
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 테마별 문제를 불러오는 중입니다...</div>';

  try {
    const res = await fetch('/api/themes');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '테마 로딩 실패');
    renderThemes(result, data.themes || []);
    _themesLoaded = true;
  } catch (e) {
    showError(result, e.message);
  }
}

function renderThemes(container, themes) {
  const withProblems = themes.filter(t => t.problems && t.problems.length > 0);
  if (withProblems.length === 0) {
    container.innerHTML = '<div class="alert alert-info">테마별 문제를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.</div>';
    return;
  }

  let html = '<div class="result-card">';
  for (const theme of withProblems) {
    html += `<div class="rec-tag-title">📚 ${escapeHtml(theme.label)}</div><div class="rec-problems">`;
    for (const p of theme.problems) {
      const ptc = tierClass(p.tier);
      html += `
        <div class="rec-problem-card cf-clickable"
             data-ref="${escapeHtml(String(p.id))}"
             data-title="${escapeHtml(p.title)}"
             data-tier="${escapeHtml(p.tier_name)}">
          <span>${escapeHtml(String(p.id))}. ${escapeHtml(p.title)}</span>
          <span class="tier-badge ${ptc}">${escapeHtml(p.tier_name)}</span>
        </div>`;
    }
    html += '</div>';
  }
  html += '</div>';
  container.innerHTML = html;

  container.querySelectorAll('.cf-clickable').forEach(el => {
    el.addEventListener('click', () => {
      openProblemModal(el.dataset.ref, el.dataset.title, el.dataset.tier);
    });
  });
}
