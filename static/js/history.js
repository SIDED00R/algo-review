const historyBtn = document.getElementById('history-btn');
historyBtn.dataset.label = '기록 불러오기';
historyBtn.addEventListener('click', loadHistory);

let allReviewProblems = [];

async function loadHistory() {
  const list = document.getElementById('history-list');
  setLoading(historyBtn, true);
  list.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 불러오는 중...</div>';

  try {
    const res = await fetch('/api/reviews/grouped');
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch (e) { throw new Error('서버 응답 오류: ' + text.slice(0, 100)); }
    if (!res.ok) throw new Error(data.detail || '실패');
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
  ctrl.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center';
  ctrl.innerHTML = `
    <input id="h-search" type="text" placeholder="제목 또는 태그 검색..." style="flex:1;min-width:140px;padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);color:var(--text);font-size:.85rem" />
    <select id="h-tier" style="padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);color:var(--text);font-size:.85rem">
      <option value="">전체 난이도</option>
      <option value="bronze">브론즈</option>
      <option value="silver">실버</option>
      <option value="gold">골드</option>
      <option value="platinum">플래티넘</option>
      <option value="diamond">다이아</option>
    </select>
    <select id="h-eff" style="padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);color:var(--text);font-size:.85rem">
      <option value="">전체 효율</option>
      <option value="good">효율적</option>
      <option value="ok">보통</option>
      <option value="poor">비효율적</option>
      <option value="${EFF_PENDING}">리뷰 대기</option>
    </select>
    <select id="h-sort" style="padding:7px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);color:var(--text);font-size:.85rem">
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
    if (q && !`${problemLabel(p)} ${p.title} ${(p.tags || []).join(' ')}`.toLowerCase().includes(q)) return false;
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
  container.querySelectorAll('.history-card, .alert').forEach(el => el.remove());

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
    const effList = p.efficiencies.split(',');
    const lastEff = effList[0];
    const div = document.createElement('div');
    div.className = 'history-card';
    div.dataset.platform = p.platform || 'boj';
    div.dataset.problemRef = p.problem_ref || String(p.problem_id || '');
    div.style.cursor = 'pointer';
    div.innerHTML = `
      <div class="history-card-info">
        <div class="history-card-title">
          <a href="${escapeHtml(problemUrl(p))}" target="_blank" rel="noopener noreferrer"
             style="color:inherit;text-decoration:none"
             onclick="event.stopPropagation()">
            ${escapeHtml(problemLabel(p))}. ${escapeHtml(p.title)}
          </a>
        </div>
        <div class="history-card-meta">${escapeHtml((p.tags || []).slice(0, 3).join(' · '))}</div>
      </div>
      <div class="history-card-right">
        ${tierBadgeHtml(tc, escapeHtml(p.tier_name || ''), 'font-size:.75rem')}
        <span class="${effClass(lastEff)}" style="font-size:.82rem">${escapeHtml(effLabel(lastEff))}</span>
        <span style="font-size:.78rem;color:var(--text-muted)">
          제출 ${escapeHtml(String(p.submission_count || 0))}회 · ${escapeHtml(String(p.last_submitted || '').slice(0, 10))}
        </span>
      </div>`;
    div.addEventListener('click', () => openReviewModal(div.dataset.platform, div.dataset.problemRef));
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

    const tabsHtml = reviews.map((r, i) => `
      <button class="submission-tab ${i === 0 ? 'active' : ''}" data-idx="${i}">
        <span style="font-weight:600">제출 ${reviews.length - i}회차</span>
        <span class="${effClass(r.efficiency)}" style="font-size:.78rem">${escapeHtml(effLabel(r.efficiency))}</span>
        <span style="color:var(--text-muted);font-size:.75rem">${escapeHtml(String(r.created_at || '').slice(0, 10))}</span>
      </button>`).join('');

    content.innerHTML = `
      <div class="problem-header" style="margin-bottom:12px">
        <span class="problem-title">
          <a href="${escapeHtml(problemUrl(first))}" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:none">
            ${escapeHtml(problemLabel(first))}. ${escapeHtml(first.title)}
          </a>
        </span>
        ${tierBadgeHtml(tc, escapeHtml(first.tier_name || ''))}
        <span style="font-size:.82rem;color:var(--text-muted);margin-left:auto">총 ${reviews.length}회 제출</span>
      </div>
      <div class="tag-list" style="margin-bottom:16px">${tagsHtml || '<span class="tag">태그 없음</span>'}</div>
      <div class="submission-tabs">${tabsHtml}</div>
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
        <div class="summary-grid" style="margin:16px 0">
          <div class="summary-item">
            <div class="summary-label">효율성</div>
            <div class="summary-value ${effClass(r.efficiency)}">${escapeHtml(effLabel(r.efficiency))}</div>
          </div>
          ${r.complexity ? `<div class="summary-item"><div class="summary-label">시간복잡도</div><div class="summary-value">${escapeHtml(r.complexity)}</div></div>` : ''}
          ${r.better_algorithm ? `<div class="summary-item"><div class="summary-label">더 나은 알고리즘</div><div class="summary-value" style="font-size:.82rem;color:var(--yellow)">${escapeHtml(r.better_algorithm)}</div></div>` : ''}
        </div>
        ${actionHtml}
        ${hasPoints ? `
        <div class="points-grid" style="margin-bottom:16px">
          <div class="points-box good"><h4>✓ 잘한 점</h4><ul>${sl || '<li>-</li>'}</ul></div>
          <div class="points-box bad"><h4>✗ 개선할 점</h4><ul>${wl || '<li>-</li>'}</ul></div>
        </div>` : ''}
        ${isPending ? '' : `
        <div class="feedback-box" style="margin-bottom:16px">
          <h4>피드백</h4>
          <div class="markdown-body">${DOMPurify.sanitize(marked.parse(r.feedback || ''))}</div>
        </div>`}
        <div>
          <h4 style="font-size:.85rem;color:var(--text-muted);margin-bottom:8px">제출 코드</h4>
          <pre class="code-block">${escapeHtml(r.code)}</pre>
        </div>`;

      document.getElementById('rereview-btn')?.addEventListener('click', runRereview);
    }

    content.querySelectorAll('.submission-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        content.querySelectorAll('.submission-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderDetail(Number(btn.dataset.idx));
      });
    });

    renderDetail(0);
  } catch (e) {
    content.innerHTML = `<div class="alert alert-error">❌ ${escapeHtml(e.message)}</div>`;
  }
}

// 재리뷰 / 문서 재업로드 액션 영역. 서버는 문제의 최신 회차를 대상으로 동작하므로
// 버튼도 최신 회차에서만 준다 — 과거 대기 회차에 버튼을 두면 눌러도 아무 일이 없다.
function buildRereviewAction(r, isPending, isLatest) {
  if (!isLatest) {
    return isPending
      ? `<div class="alert alert-info" style="margin-bottom:12px">
           ⏳ 리뷰 대기 회차입니다. 이후 회차에 리뷰가 있어 이 회차는 대기 상태로 남습니다.
         </div>`
      : '';
  }

  const label = isPending ? '🤖 지금 AI 리뷰 실행' : '📤 GitHub 문서 다시 올리기';
  const notice = isPending
    ? `<div class="alert alert-info" style="margin-bottom:12px">
         ⏳ AI 리뷰 대기 중입니다. LLM을 쓸 수 있을 때 아래 버튼을 누르면 리뷰 기록과 GitHub README가 함께 갱신됩니다.
       </div>`
    : '';
  return `${notice}
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
      <button id="rereview-btn" class="btn-primary" style="font-size:.85rem;padding:7px 16px"
        data-platform="${escapeHtml(r.platform)}" data-problem-ref="${escapeHtml(r.problem_ref)}"
        data-label="${escapeHtml(label)}">
        ${label}
      </button>
      <span id="rereview-msg" style="font-size:.82rem"></span>
    </div>`;
}

async function runRereview(e) {
  const btn = e.currentTarget;
  const msg = document.getElementById('rereview-msg');
  const platform = btn.dataset.platform;
  const problemRef = btn.dataset.problemRef;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 처리 중... (리뷰는 10~20초)';
  msg.textContent = '';
  msg.style.color = '';

  try {
    const data = await fetchJsonOk(
      `/api/rereview/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`,
      { method: 'POST' }, '재리뷰 실패');
    if (!data.pushed) {
      alert(`${data.detail || 'GitHub 갱신에 실패했습니다.'}\n\n` +
            "최신 회차의 '📤 GitHub 문서 다시 올리기' 버튼으로 업로드만 재시도할 수 있습니다 (리뷰는 다시 돌리지 않습니다).");
    }
    await openReviewModal(platform, problemRef);  // 갱신된 리뷰로 모달 재렌더
    loadHistory();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = btn.dataset.label;
    msg.textContent = err.message;
    msg.style.color = 'var(--red)';
  }
}

document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('review-modal').classList.add('hidden');
});
document.getElementById('review-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
});
