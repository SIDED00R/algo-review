let selectedStatsPlatform = 'boj';

const statsBtn = document.getElementById('stats-btn');
statsBtn.dataset.label = '통계 불러오기';

document.querySelectorAll('.btn-toggle[data-platform]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.btn-toggle[data-platform]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedStatsPlatform = btn.dataset.platform;
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
    const barColor = poorRatio > 0.6 ? 'var(--red)' : poorRatio > 0.3 ? 'var(--yellow)' : 'var(--green)';
    return `
      <div class="stat-bar-row">
        <span class="stat-tag-name" title="${s.tag}">${s.tag}</span>
        <div class="stat-bar-wrap">
          <div class="stat-bar" style="width:${Math.round(poorRatio*100)}%;background:${barColor}"></div>
        </div>
        <span class="stat-counts">✓${s.good_count} ✗${s.poor_count}</span>
      </div>`;
  }).join('');

  let historyHtml = data.history.map(r => {
    const tc = isCf ? '' : tierClass(r.tier);
    const tierLabel = tierBadgeHtml(tc, r.tier_name, 'font-size:.75rem');
    return `<tr>
      <td><a href="${problemUrl(r)}" target="_blank">${problemLabel(r)}. ${r.title}</a></td>
      <td>${tierLabel}</td>
      <td class="${effClass(r.efficiency)}">${effLabel(r.efficiency)}</td>
      <td style="color:var(--text-muted);font-size:.82rem">${r.created_at.slice(0,10)}</td>
    </tr>`;
  }).join('');

  const levelLabel = isCf ? '평균 레이팅' : '평균 레벨';
  const levelValue = isCf
    ? `<span style="font-weight:700">${data.avg_tier_name}</span>`
    : tierBadgeHtml(tierClass(Math.floor(data.avg_tier)), data.avg_tier_name);

  container.innerHTML = `
    <div class="result-card">
      <div class="summary-grid" style="margin-bottom:24px">
        <div class="summary-item">
          <div class="summary-label">총 리뷰 수</div>
          <div class="summary-value">${data.total_reviews}개</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">${levelLabel}</div>
          <div class="summary-value">${levelValue}</div>
        </div>
      </div>
      <h3 style="font-size:.95rem;margin-bottom:14px;color:var(--text-muted)">태그별 취약도 (빨간색일수록 취약)</h3>
      ${barsHtml}
      <h3 style="font-size:.95rem;margin:24px 0 12px;color:var(--text-muted)">최근 풀이 기록</h3>
      ${data.history.length === 0
        ? '<p style="color:var(--text-muted);font-size:.88rem">최근 기록이 없습니다.</p>'
        : `<table class="history-table">
            <thead><tr><th>문제</th><th>난이도</th><th>평가</th><th>날짜</th></tr></thead>
            <tbody>${historyHtml}</tbody>
          </table>`
      }
    </div>`;
}
