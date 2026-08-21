const recommendBtn = document.getElementById('recommend-btn');
recommendBtn.dataset.label = '추천받기';

// 현재 세션에서 이미 본 문제 ID 목록 (페이지 이탈 시 자동 초기화)
const _shownIds = new Set();

async function fetchRecommend(excludeIds = new Set()) {
  const result = document.getElementById('recommend-result');
  setLoading(recommendBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 추천 문제를 검색 중입니다...</div>';

  try {
    const platform = document.getElementById('recommend-platform')?.value || 'codeforces';
    const excludeParam = excludeIds.size > 0 ? `&exclude=${[...excludeIds].join(',')}` : '';
    const data = await fetchJsonOk(`/api/recommend?platform=${encodeURIComponent(platform)}${excludeParam}`, undefined, '추천 실패');
    renderRecommend(result, data);
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(recommendBtn, false);
  }
}

recommendBtn.addEventListener('click', () => fetchRecommend());

function renderRecommend(container, data) {
  if (!data.recommendations || data.recommendations.length === 0) {
    container.innerHTML = `
      <div class="alert alert-info">
        아직 추천 데이터가 없습니다. 먼저 코드 리뷰를 몇 개 진행해보세요.
      </div>`;
    return;
  }

  const tc = tierClass(Math.floor(data.avg_tier));
  let html = `
    <div class="result-card">
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">현재 평균 레벨 (최근 30개)</div>
          <div class="summary-value">${tierBadgeHtml(tc, escapeHtml(data.tier_name))}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">추천 난이도 범위</div>
          <div class="summary-value summary-value-sm">${escapeHtml(data.tier_range || '-')}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">취약 태그</div>
          <div class="summary-value summary-value-sm">${escapeHtml((data.weak_tags || []).join(', '))}</div>
        </div>
      </div>
  `;

  for (const rec of data.recommendations) {
    html += `<div class="rec-tag-title">${escapeHtml(rec.tag)}</div><div class="rec-problems">`;
    for (const p of rec.problems) {
      const ptc = tierClass(p.tier);
      const isCF = p.url && p.url.includes('codeforces');
      if (isCF) {
        html += `
          <div class="rec-problem-card cf-clickable"
               data-ref="${escapeHtml(String(p.id))}"
               data-title="${escapeHtml(p.title)}"
               data-tier="${escapeHtml(p.tier_name)}">
            <span>${escapeHtml(String(p.id))}. ${escapeHtml(p.title)}</span>
            ${tierBadgeHtml(ptc, escapeHtml(p.tier_name))}
          </div>`;
      } else {
        html += `
          <div class="rec-problem-card">
            <a href="${escapeHtml(p.url || 'https://boj.kr/' + p.id)}" target="_blank">${escapeHtml(String(p.id))}. ${escapeHtml(p.title)}</a>
            ${tierBadgeHtml(ptc, escapeHtml(p.tier_name))}
          </div>`;
      }
    }
    html += `</div>`;
  }
  html += `</div>
    <div class="action-row action-row-center">
      <button id="recommend-reset-btn" class="btn-secondary">다른 목록 추천받기</button>
    </div>`;
  container.innerHTML = html;

  for (const rec of data.recommendations) {
    for (const p of rec.problems) {
      _shownIds.add(String(p.id));
    }
  }

  bindCfProblemClicks(container);

  document.getElementById('recommend-reset-btn').addEventListener('click', () => fetchRecommend(new Set(_shownIds)));
}
