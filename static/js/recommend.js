const recommendBtn = document.getElementById('recommend-btn');
recommendBtn.dataset.label = '추천받기';
recommendBtn.dataset.loadingLabel = '추천 계산 중...';

// 이번 세션에서 이미 본 문제 ID. `&exclude=` 쿼리스트링에 통째로 실리므로 상한을 둔다.
// Set 은 삽입 순서를 유지하므로 앞(오래된 것)부터 버린다.
const _SHOWN_ID_LIMIT = 300;
const _shownIds = new Set();

// 세대 토큰 — 플랫폼을 바꿔 연속 요청하면 늦게 온 이전 플랫폼 응답이 새 결과를 덮는다.
let _recommendToken = 0;

// 플랫폼을 바꾸면 이전 결과를 지운다 — 토글과 화면이 다른 플랫폼을 가리키면 안 된다.
// 자동 재요청은 하지 않는다(추천은 외부 검색 API 를 여러 번 친다).
document.getElementById('recommend-platform')?.addEventListener('change', () => {
  _shownIds.clear();   // 세션 캐시도 플랫폼별이다 — CF id 가 BOJ 요청의 exclude 로 나간다
  const result = document.getElementById('recommend-result');
  if (result.innerHTML.trim()) {
    // 진행 중인 이전 플랫폼 요청을 무효화한다. 그 요청의 finally 는 토큰이 갈려
    // 버튼을 되돌리지 않으므로, 무효화한 쪽에서 버튼 상태도 함께 되돌린다.
    _recommendToken++;
    setLoading(recommendBtn, false);
    result.innerHTML =
      '<div class="alert alert-info">플랫폼을 바꿨습니다. \'추천받기\'를 눌러주세요.</div>';
  }
});

function rememberShownId(id) {
  _shownIds.add(String(id));
  while (_shownIds.size > _SHOWN_ID_LIMIT) {
    _shownIds.delete(_shownIds.values().next().value);
  }
}

async function fetchRecommend(excludeIds = new Set()) {
  const result = document.getElementById('recommend-result');
  const token = ++_recommendToken;
  setLoading(recommendBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 추천 문제를 검색 중입니다...</div>';

  try {
    const platform = document.getElementById('recommend-platform')?.value || 'codeforces';
    const excludeParam = excludeIds.size > 0 ? `&exclude=${[...excludeIds].join(',')}` : '';
    const data = await fetchJsonOk(`/api/recommend?platform=${encodeURIComponent(platform)}${excludeParam}`, undefined, '추천 실패');
    if (token !== _recommendToken) return;
    renderRecommend(result, data);
  } catch (e) {
    if (token !== _recommendToken) return;
    showError(result, e.message);
  } finally {
    if (token === _recommendToken) setLoading(recommendBtn, false);
  }
}

recommendBtn.addEventListener('click', () => fetchRecommend());

function renderRecommend(container, data) {
  if (!data.recommendations || data.recommendations.length === 0) {
    // 검색 실패와 "기록이 없어서 빈 결과" 를 구분한다. 서버가 error 를 주면 그 이유를
    // 그대로 보인다.
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
