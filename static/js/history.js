const historyBtn = document.getElementById('history-btn');
historyBtn.dataset.label = '기록 불러오기';
historyBtn.dataset.loadingLabel = '불러오는 중...';
historyBtn.addEventListener('click', loadHistory);

let allReviewProblems = [];

async function loadHistory() {
  const list = document.getElementById('history-list');
  setLoading(historyBtn, true);
  list.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 불러오는 중...</div>';

  try {
    const data = await fetchJsonOk('/api/reviews/grouped', undefined, '기록 로딩 실패');
    allReviewProblems = data.problems || [];
    renderHistoryControls(list);
    renderProblemList(list, getFilteredReviews());
  } catch (e) {
    showError(list, e.message);
  } finally {
    setLoading(historyBtn, false);
  }
}

function renderHistoryControls(container) {
  const ctrl = document.createElement('div');
  ctrl.id = 'history-controls';
  ctrl.className = 'toolbar';
  ctrl.innerHTML = `
    <input id="h-search" class="input filter-grow" type="text" placeholder="제목 또는 태그 검색..." />
    <select id="h-tier" class="select filter-fixed" aria-label="난이도 필터">
      <option value="">전체 난이도</option>
      <option value="bronze">브론즈</option>
      <option value="silver">실버</option>
      <option value="gold">골드</option>
      <option value="platinum">플래티넘</option>
      <option value="diamond">다이아</option>
    </select>
    <select id="h-eff" class="select filter-fixed" aria-label="효율 필터">
      <option value="">전체 효율</option>
      <option value="good">효율적</option>
      <option value="ok">보통</option>
      <option value="poor">비효율적</option>
      <option value="${EFF_PENDING}">리뷰 대기</option>
    </select>
    <select id="h-sort" class="select filter-fixed" aria-label="정렬">
      <option value="recent">최근순</option>
      <option value="tier_desc">난이도 높은순</option>
      <option value="tier_asc">난이도 낮은순</option>
      <option value="pid_asc">문제 번호순</option>
    </select>`;
  container.innerHTML = '';
  container.appendChild(ctrl);

  ['h-search', 'h-tier', 'h-eff', 'h-sort'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => {
      renderProblemList(container, getFilteredReviews());
    });
  });
}

function getFilteredReviews() {
  const q = (document.getElementById('h-search')?.value || '').toLowerCase();
  const tier = document.getElementById('h-tier')?.value || '';
  const eff = document.getElementById('h-eff')?.value || '';
  const sort = document.getElementById('h-sort')?.value || 'recent';

  let list = allReviewProblems.filter(p => {
    if (!matchesProblemQuery(p, q)) return false;
    if (tier && !tierInGroup(p.tier, tier)) return false;
    if (eff) {
      const lastEff = p.efficiencies.split(',')[0];
      if (lastEff !== eff) return false;
    }
    return true;
  });

  if (sort === 'recent') list.sort((a, b) => b.last_submitted.localeCompare(a.last_submitted));
  else if (sort === 'tier_desc') list.sort((a, b) => b.tier - a.tier);
  else if (sort === 'tier_asc') list.sort((a, b) => a.tier - b.tier);
  else if (sort === 'pid_asc') list.sort(compareProblemLabel);
  return list;
}

function renderProblemList(container, problems) {
  container.querySelectorAll('.row, .alert').forEach(el => el.remove());

  if (!problems || problems.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'alert alert-info';
    empty.textContent = '아직 리뷰 기록이 없습니다.';
    container.appendChild(empty);
    return;
  }

  const frag = document.createDocumentFragment();
  problems.forEach(p => {
    const tc = tierClass(p.tier);
    const lastEff = p.efficiencies.split(',')[0];
    const div = document.createElement('div');
    div.className = 'row';
    div.dataset.platform = p.platform || 'boj';
    div.dataset.problemRef = p.problem_ref || String(p.problem_id || '');
    div.innerHTML = `
      <div class="row-main">
        <div class="row-title">
          <a href="${escapeHtml(problemUrl(p))}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(problemLabel(p))}. ${escapeHtml(p.title)}
          </a>
        </div>
        <div class="row-meta">${escapeHtml((p.tags || []).slice(0, 3).join(' · '))}</div>
      </div>
      <div class="row-side">
        ${tierBadgeHtml(tc, escapeHtml(p.tier_name || ''))}
        <span class="${effClass(lastEff)}">${escapeHtml(effLabel(lastEff))}</span>
        <span class="row-dim">제출 ${escapeHtml(String(p.submission_count || 0))}회 · ${escapeHtml(String(p.last_submitted || '').slice(0, 10))}</span>
      </div>`;
    makeRowActivatable(div, () => openReviewModal(div.dataset.platform, div.dataset.problemRef));
    frag.appendChild(div);
  });
  container.appendChild(frag);
}

async function openReviewModal(platform, problemRef) {
  const modal = document.getElementById('review-modal');
  const content = document.getElementById('modal-content');
  modal.classList.remove('hidden');
  content.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 불러오는 중...</div>';

  try {
    const data = await fetchJsonOk(`/api/reviews/problem/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`, undefined, '실패');
    const reviews = data.reviews;
    if (!reviews.length) throw new Error('기록이 없습니다.');

    const first = reviews[0];
    const tc = tierClass(first.tier);
    const tagsHtml = (first.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');

    // 제출 원장 — 회차·날짜·복잡도·판정을 모노로 정렬한다.
    const ledgerHtml = reviews.map((r, i) => `
      <button class="ledger-row ${i === 0 ? 'active' : ''}" data-idx="${i}">
        <span class="ledger-seq">#${reviews.length - i}</span>
        <span>${escapeHtml(String(r.created_at || '').slice(0, 10))}</span>
        <span class="ledger-meta">${escapeHtml(r.complexity || '-')}</span>
        <span class="${effClass(r.efficiency)}">${escapeHtml(effLabel(r.efficiency))}</span>
      </button>`).join('');

    content.innerHTML = `
      <div class="problem-header">
        <span class="problem-title">
          <a href="${escapeHtml(problemUrl(first))}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(problemLabel(first))}. ${escapeHtml(first.title)}
          </a>
        </span>
        ${tierBadgeHtml(tc, escapeHtml(first.tier_name || ''))}
        <span class="hint push-right">총 ${reviews.length}회 제출</span>
      </div>
      <div class="tag-list">${tagsHtml || '<span class="tag">태그 없음</span>'}</div>
      <div class="ledger">${ledgerHtml}</div>
      <div id="submission-detail-area"></div>`;

    function renderDetail(idx) {
      const r = reviews[idx];
      const isPending = r.efficiency === EFF_PENDING;
      const sl = (r.strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('');
      const wl = (r.weaknesses || []).map(w => `<li>${escapeHtml(w)}</li>`).join('');
      const hasPoints = sl || wl;
      // idx 0 이 최신 회차 — 서버의 재리뷰/재푸시는 문제의 최신 회차를 대상으로 동작한다.
      const actionHtml = buildRereviewAction(r, isPending, idx === 0);
      document.getElementById('submission-detail-area').innerHTML = `
        <div class="summary-grid">
          <div class="summary-item">
            <div class="summary-label">효율성</div>
            <div class="summary-value ${effClass(r.efficiency)}">${escapeHtml(effLabel(r.efficiency))}</div>
          </div>
          ${r.complexity ? `<div class="summary-item"><div class="summary-label">시간복잡도</div><div class="summary-value">${escapeHtml(r.complexity)}</div></div>` : ''}
          ${r.better_algorithm ? `<div class="summary-item"><div class="summary-label">더 나은 알고리즘</div><div class="summary-value summary-value-sm">${escapeHtml(r.better_algorithm)}</div></div>` : ''}
        </div>
        ${actionHtml}
        ${hasPoints ? `
        <div class="points-grid">
          <div class="points-box good"><h4>잘한 점</h4><ul>${sl || '<li>-</li>'}</ul></div>
          <div class="points-box bad"><h4>개선할 점</h4><ul>${wl || '<li>-</li>'}</ul></div>
        </div>` : ''}
        ${isPending ? '' : `
        <div class="feedback-box">
          <h4>피드백</h4>
          <div class="markdown-body">${renderMarkdown(r.feedback)}</div>
        </div>`}
        <div class="code-section">
          <div class="field-head">
            <span class="label">제출 코드</span>
            <button type="button" id="reuse-code-btn" class="btn-ghost">이 코드로 다시 풀기</button>
          </div>
          <pre class="code-block">${escapeHtml(r.code)}</pre>
        </div>`;

      document.getElementById('rereview-btn')?.addEventListener('click', runRereview);
      // 모든 회차에 준다 — 재리뷰는 서버가 최신 회차만 다루지만 불러오기는
      // 순수 클라이언트 동작이라 과거 회차에도 유효하다.
      document.getElementById('reuse-code-btn').addEventListener('click', () => {
        if (!confirmEditorOverwrite()) return;
        closeReviewModal();
        fillReviewForm(r, reviews.length - idx, reviews.length);
      });
    }

    content.querySelectorAll('.ledger-row').forEach(btn => {
      btn.addEventListener('click', () => {
        content.querySelectorAll('.ledger-row').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderDetail(Number(btn.dataset.idx));
      });
    });

    renderDetail(0);
  } catch (e) {
    content.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}

// 재리뷰 / 문서 재업로드 액션 영역. 서버는 문제의 최신 회차를 대상으로 동작하므로
// 버튼도 최신 회차에서만 준다 — 과거 회차에 버튼을 두면 눌러도 아무 일이 없다.
function buildRereviewAction(r, isPending, isLatest) {
  if (!isLatest) {
    return isPending
      ? `<div class="alert alert-info">
           리뷰 대기 회차입니다. 이후 회차에 리뷰가 있어 이 회차는 대기 상태로 남습니다.
         </div>`
      : '';
  }

  const label = isPending ? '지금 AI 리뷰 실행' : 'GitHub 문서 다시 올리기';
  const notice = isPending
    ? `<div class="alert alert-info">
         AI 리뷰 대기 중입니다. LLM을 쓸 수 있을 때 아래 버튼을 누르면 리뷰 기록과 GitHub README가 함께 갱신됩니다.
       </div>`
    : '';
  return `${notice}
    <div class="action-row">
      <button id="rereview-btn" class="btn-primary btn-sm"
        data-platform="${escapeHtml(r.platform)}" data-problem-ref="${escapeHtml(r.problem_ref)}"
        data-label="${escapeHtml(label)}" data-loading-label="처리 중... (리뷰는 10~20초)">
        ${label}
      </button>
      <span id="rereview-msg" class="action-msg"></span>
    </div>`;
}

async function runRereview(e) {
  const btn = e.currentTarget;
  const msg = document.getElementById('rereview-msg');
  const platform = btn.dataset.platform;
  const problemRef = btn.dataset.problemRef;
  setLoading(btn, true);
  msg.textContent = '';
  msg.className = 'action-msg';

  try {
    const data = await fetchJsonOk(
      `/api/rereview/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`,
      { method: 'POST' }, '재리뷰 실패');
    if (!data.pushed) {
      alert(`${data.detail || 'GitHub 갱신에 실패했습니다.'}\n\n` +
            "최신 회차의 'GitHub 문서 다시 올리기' 버튼으로 업로드만 재시도할 수 있습니다 (리뷰는 다시 돌리지 않습니다).");
    }
    await openReviewModal(platform, problemRef);  // 갱신된 리뷰로 모달 재렌더
    loadHistory();
  } catch (err) {
    setLoading(btn, false);
    msg.textContent = err.message;
    msg.classList.add('bad');
  }
}

// 모달은 #tab-history 안에 있다 — 닫지 않고 탭을 옮기면 그대로 남으므로
// 닫기 경로를 한 곳으로 모은다.
function closeReviewModal() {
  document.getElementById('review-modal').classList.add('hidden');
}

document.getElementById('modal-close').addEventListener('click', closeReviewModal);
// Esc·포커스 트랩·초기 포커스는 공통 모듈이 담당한다 — 예전에는 이 모달만 셋 다 없었다.
registerModal('review-modal', closeReviewModal, { initial: '#modal-close' });
document.getElementById('review-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeReviewModal();
});
