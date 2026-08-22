const recommendBtn = document.getElementById('recommend-btn');
recommendBtn.dataset.label = '추천받기';
recommendBtn.dataset.loadingLabel = '추천 계산 중...';

// 현재 세션에서 이미 본 문제 ID 목록 (페이지 이탈 시 자동 초기화).
// 통째로 `&exclude=` 쿼리스트링에 실리므로 상한을 둔다 — 없으면 "다른 목록 추천받기" 를
// 누를 때마다 회당 15개씩 무한히 늘어나 URL 길이 한계에 걸린다. Set 은 삽입 순서를
// 유지하므로 앞(오래된 것)부터 버리면 최근에 본 것이 남는다.
const _SHOWN_ID_LIMIT = 300;
const _shownIds = new Set();

function rememberShownId(id) {
  _shownIds.add(String(id));
  while (_shownIds.size > _SHOWN_ID_LIMIT) {
    _shownIds.delete(_shownIds.values().next().value);
  }
}

// 세대 토큰이 없는 유일한 비동기 렌더 경로다. 리셋 버튼은 매 렌더마다 새로 만들어지고
// setLoading 이 추천 버튼을 disabled 로 만들어, 이 함수가 겹쳐 도는 경로가 없다.
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
    // 검색 실패와 "기록이 없어서 빈 결과" 를 구분한다 — 서버가 error 를 주면 그 이유를
    // 그대로 보인다. 구분하지 않으면 외부 API 장애를 사용자 탓으로 표시하게 된다.
    container.innerHTML = data.error
      ? `<div class="alert alert-error">${escapeHtml(data.error)} 잠시 후 다시 시도해주세요.</div>`
      : `<div class="alert alert-info">
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

  // 플랫폼 판정은 응답의 platform 필드 하나로 한다 — URL 부분문자열로 따로 판정하면
  // 같은 질의가 두 술어에서 다른 결과를 준다.
  const isCF = data.platform === 'codeforces';

  for (const rec of data.recommendations) {
    html += `<div class="rec-tag-title">${escapeHtml(rec.tag)}</div><div class="rec-problems">`;
    for (const p of rec.problems) {
      const ptc = tierClass(p.tier);
      if (isCF) {
        html += `
          <div class="rec-problem-card is-clickable"
               data-ref="${escapeHtml(String(p.id))}"
               data-title="${escapeHtml(p.title)}"
               data-tier="${escapeHtml(p.tier_name)}">
            <span>${escapeHtml(String(p.id))}. ${escapeHtml(p.title)}</span>
            ${tierBadgeHtml(ptc, escapeHtml(p.tier_name))}
          </div>`;
      } else {
        html += `
          <div class="rec-problem-card">
            <a href="${escapeHtml(p.url || 'https://boj.kr/' + p.id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(String(p.id))}. ${escapeHtml(p.title)}</a>
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
      rememberShownId(p.id);
    }
  }

  bindCfProblemClicks(container);

  document.getElementById('recommend-reset-btn').addEventListener('click', () => fetchRecommend(new Set(_shownIds)));
}
