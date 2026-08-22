let selectedStatsPlatform = 'boj';

const statsBtn = document.getElementById('stats-btn');
statsBtn.dataset.label = '통계 불러오기';
statsBtn.dataset.loadingLabel = '집계 중...';

// 요청 세대 토큰 — 플랫폼을 연속으로 바꾸면 늦게 도착한 이전 플랫폼 응답이
// 새 토글 상태와 함께 렌더된다(fetch 시작 시점의 platform 으로 조회되므로).
let _statsToken = 0;

async function loadStats() {
  const result = document.getElementById('stats-result');
  const platform = selectedStatsPlatform;
  const token = ++_statsToken;
  setLoading(statsBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 불러오는 중...</div>';

  try {
    const data = await fetchJsonOk(`/api/stats?platform=${platform}`, undefined, '실패');
    if (token !== _statsToken) return;
    renderStats(result, data);
  } catch (e) {
    if (token !== _statsToken) return;
    showError(result, e.message);
  } finally {
    if (token === _statsToken) setLoading(statsBtn, false);
  }
}

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
    // 이미 결과가 떠 있으면 다시 받는다 — 토글과 표가 다른 플랫폼을 가리키면 안 된다.
    // loadStats 를 직접 부른다. statsBtn.click() 은 setLoading 이 disabled 로 만든
    // 버튼에서 명세상 이벤트를 디스패치하지 않아 재요청이 조용히 무시된다.
    if (document.getElementById('stats-result').innerHTML.trim()) loadStats();
  });
});

statsBtn.addEventListener('click', loadStats);

function renderStats(container, data) {
  if (!data.tag_stats || data.tag_stats.length === 0) {
    container.innerHTML = '<div class="alert alert-info">아직 데이터가 없습니다.</div>';
    return;
  }

  const isCf = data.platform === 'codeforces';

  let barsHtml = data.tag_stats.slice(0, 15).map(s => {
    const poorRatio = s.total_count > 0 ? s.poor_count / s.total_count : 0;
    const barColor = poorRatio > 0.6 ? 'var(--bar-high)'
      : poorRatio > 0.3 ? 'var(--bar-mid)' : 'var(--bar-low)';
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
      <td><a href="${escapeHtml(problemUrl(r))}" target="_blank" rel="noopener noreferrer">${escapeHtml(problemLabel(r))}. ${escapeHtml(r.title)}</a></td>
      <td>${tierLabel}</td>
      <td class="${effClass(r.efficiency)}">${escapeHtml(effLabel(r.efficiency))}</td>
      <td class="td-dim">${escapeHtml(String(r.created_at || '').slice(0, 10))}</td>
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
