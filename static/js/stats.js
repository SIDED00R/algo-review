let selectedStatsPlatform = 'boj';

const statsBtn = document.getElementById('stats-btn');
statsBtn.dataset.label = '통계 불러오기';
statsBtn.dataset.loadingLabel = '집계 중...';

document.querySelectorAll('.btn-toggle[data-platform]').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.platform === selectedStatsPlatform) return;
    document.querySelectorAll('.btn-toggle[data-platform]').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-pressed', 'false');
    });
    btn.classList.add('active');
    btn.setAttribute('aria-pressed', 'true');
    selectedStatsPlatform = btn.dataset.platform;
    // 이미 결과가 떠 있으면 다시 받는다 — 예전에는 토글만 바뀌고 표는 옛 플랫폼 것이
    // 그대로 남아, 사용자가 '통계 불러오기'를 다시 눌러야 맞았다(테마 탭은 재요청한다).
    if (document.getElementById('stats-result').innerHTML.trim()) statsBtn.click();
  });
});

statsBtn.addEventListener('click', async () => {
  const result = document.getElementById('stats-result');
  setLoading(statsBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 불러오는 중...</div>';

  try {
    const data = await fetchJsonOk(`/api/stats?platform=${selectedStatsPlatform}`, undefined, '실패');
    renderStats(result, data);
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(statsBtn, false);
  }
});

function renderStats(container, data) {
  if (!data.tag_stats || data.tag_stats.length === 0) {
    container.innerHTML = '<div class="alert alert-info">아직 데이터가 없습니다.</div>';
    return;
  }

  const isCf = data.platform === 'codeforces';

  let barsHtml = data.tag_stats.slice(0, 15).map(s => {
    const poorRatio = s.total_count > 0 ? s.poor_count / s.total_count : 0;
    const barColor = poorRatio > 0.6 ? 'var(--eff-poor-fg)'
      : poorRatio > 0.3 ? 'var(--eff-ok-fg)' : 'var(--eff-good-fg)';
    return `
      <div class="stat-bar-row">
        <span class="stat-tag-name" title="${escapeHtml(s.tag)}">${escapeHtml(s.tag)}</span>
        <div class="stat-bar-wrap">
          <div class="stat-bar" style="width:${Math.round(poorRatio*100)}%;background:${barColor}"></div>
        </div>
        <span class="stat-counts">✓${s.good_count} ✗${s.poor_count}</span>
      </div>`;
  }).join('');

  let historyHtml = data.history.map(r => {
    const tc = isCf ? '' : tierClass(r.tier);
    const tierLabel = tierBadgeHtml(tc, escapeHtml(r.tier_name));
    return `<tr>
      <td><a href="${escapeHtml(problemUrl(r))}" target="_blank">${escapeHtml(problemLabel(r))}. ${escapeHtml(r.title)}</a></td>
      <td>${tierLabel}</td>
      <td class="${effClass(r.efficiency)}">${effLabel(r.efficiency)}</td>
      <td class="td-dim">${r.created_at.slice(0,10)}</td>
    </tr>`;
  }).join('');

  const levelLabel = isCf ? '평균 레이팅' : '평균 레벨';
  const levelValue = isCf
    ? `<span class="mono">${escapeHtml(data.avg_tier_name)}</span>`
    : tierBadgeHtml(tierClass(Math.floor(data.avg_tier)), escapeHtml(data.avg_tier_name));

  container.innerHTML = `
    <div class="result-card">
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">총 리뷰 수</div>
          <div class="summary-value">${data.total_reviews}개</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">${levelLabel}</div>
          <div class="summary-value">${levelValue}</div>
        </div>
      </div>
      <h3 class="section-title">태그별 취약도 (빨간색일수록 취약)</h3>
      ${barsHtml}
      <h3 class="section-title section-title-gap">최근 풀이 기록</h3>
      ${data.history.length === 0
        ? '<p class="hint">최근 기록이 없습니다.</p>'
        : `<table class="history-table">
            <thead><tr><th>문제</th><th>난이도</th><th>평가</th><th>날짜</th></tr></thead>
            <tbody>${historyHtml}</tbody>
          </table>`
      }
    </div>`;
}
