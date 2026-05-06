/* 코드 리뷰 탭 — 코드 리뷰 요청 및 결과 렌더링만 담당 */

const platformSelect = document.getElementById('problem-platform');
const problemIdInput = document.getElementById('problem-id');
const problemIdLabel = document.getElementById('problem-id-label');
const problemIdHelp = document.getElementById('problem-id-help');

function syncProblemInputUI() {
  const platform = platformSelect?.value || 'boj';
  if (platform === 'codeforces') {
    problemIdLabel.textContent = '문제 번호';
    problemIdInput.placeholder = '예) 4A 또는 4/A';
    problemIdHelp.textContent = 'Codeforces: contestId + index 형식으로 입력하세요. 예) 4A, 4/A';
  } else {
    problemIdLabel.textContent = '문제 번호';
    problemIdInput.placeholder = '예) 1000';
    problemIdHelp.textContent = '백준: 숫자만 입력하세요. 예) 1000';
  }
}

platformSelect?.addEventListener('change', syncProblemInputUI);
syncProblemInputUI();

const reviewBtn = document.getElementById('review-btn');
reviewBtn.dataset.label = '분석 시작';

reviewBtn.addEventListener('click', async () => {
  const platform = platformSelect?.value || 'boj';
  const problemId = document.getElementById('problem-id').value.trim();
  const problemStatement = document.getElementById('problem-statement').value.trim();
  const code = window.getEditorValue('code-input').trim();
  const result = document.getElementById('review-result');

  if (!problemId) { showError(result, '문제 번호를 입력하세요.'); return; }
  if (!code) { showError(result, '코드를 입력하세요.'); return; }

  setLoading(reviewBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 코드를 분석 중입니다... (10~20초 소요)</div>';
  result.classList.remove('hidden');

  try {
    const payload = { platform, code, problem_statement: problemStatement || null };
    if (platform === 'codeforces') payload.problem_ref = problemId;
    else payload.problem_id = Number(problemId);

    const res = await fetch('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '분석 실패');
    renderReview(result, data);
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(reviewBtn, false);
  }
});

function renderReview(container, d) {
  const tc = tierClass(d.tier);
  const tagsHtml = d.tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
  const strengthsHtml = (d.strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('') || '<li>-</li>';
  const weaknessesHtml = (d.weaknesses || []).map(w => `<li>${escapeHtml(w)}</li>`).join('') || '<li>-</li>';
  const feedbackHtml = marked.parse(d.feedback || '');
  const label = escapeHtml(problemLabel(d));
  const title = escapeHtml(d.title);
  const tierName = escapeHtml(d.tier_name);
  const betterAlgo = d.better_algorithm
    ? `<div class="summary-item"><div class="summary-label">더 나은 알고리즘</div><div class="summary-value" style="font-size:.85rem;color:var(--yellow)">${escapeHtml(d.better_algorithm)}</div></div>`
    : '';

  container.innerHTML = `
    <div class="result-card">
      <div class="problem-header">
        <span class="problem-title">
          <a href="${escapeHtml(problemUrl(d))}" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:none">
            ${label}. ${title}
          </a>
        </span>
        <span class="tier-badge ${tc}">${tierName}</span>
      </div>
      <div class="tag-list">${tagsHtml || '<span class="tag">태그 없음</span>'}</div>
      <div class="summary-grid">
        <div class="summary-item">
          <div class="summary-label">효율성 평가</div>
          <div class="summary-value ${effClass(d.efficiency)}">${escapeHtml(effLabel(d.efficiency))}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">시간복잡도</div>
          <div class="summary-value">${escapeHtml(d.complexity || 'N/A')}</div>
        </div>
        ${betterAlgo}
      </div>
      <div class="points-grid">
        <div class="points-box good"><h4>✓ 잘한 점</h4><ul>${strengthsHtml}</ul></div>
        <div class="points-box bad"><h4>✗ 개선할 점</h4><ul>${weaknessesHtml}</ul></div>
      </div>
      <div class="feedback-box">
        <h4>상세 피드백</h4>
        <div class="markdown-body">${feedbackHtml}</div>
      </div>
      <div style="margin-top:16px;display:flex;align-items:center;gap:10px">
        <button id="push-github-btn" class="btn-primary" style="font-size:.85rem;padding:7px 16px">
          🐙 GitHub에 올리기
        </button>
        <span id="push-github-msg" style="font-size:.82rem"></span>
      </div>
    </div>
  `;

  document.getElementById('push-github-btn').addEventListener('click', async () => {
    const btn = document.getElementById('push-github-btn');
    const msg = document.getElementById('push-github-msg');
    const code = window.getEditorValue('code-input').trim();
    const langSelect = document.getElementById('code-language');
    const language = (langSelect && langSelect.value) || detectLanguage(code);
    btn.disabled = true;
    btn.textContent = '올리는 중...';
    msg.textContent = '';
    msg.style.color = '';
    try {
      const res = await fetch('/api/push-review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: d.platform,
          problem_ref: d.problem_ref,
          title: d.title,
          tier_name: d.tier_name,
          tags: d.tags,
          code,
          language,
          url: d.problem_url,
          ...(d.platform === 'codeforces' && _currentProblem?.ref === d.problem_ref ? {
            description: _currentProblem.sections?.statement || '',
            input_desc: _currentProblem.sections?.input || '',
            output_desc: _currentProblem.sections?.output || '',
          } : {}),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'push 실패');
      btn.textContent = '✓ 완료';
      msg.innerHTML = `<span style="color:var(--green)">🐙 <b>${escapeHtml(data.repo || '')}</b>에 push 완료</span>`;
    } catch (e) {
      btn.textContent = '🐙 GitHub에 올리기';
      btn.disabled = false;
      msg.textContent = e.message;
      msg.style.color = 'var(--red)';
    }
  });
}
