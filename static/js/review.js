const platformSelect = document.getElementById('problem-platform');
const problemIdInput = document.getElementById('problem-id');
const problemIdHelp = document.getElementById('problem-id-help');

function syncProblemInputUI() {
  const platform = platformSelect.value || 'boj';
  if (platform === 'codeforces') {
    problemIdInput.placeholder = '예) 4A 또는 4/A';
    problemIdHelp.textContent = 'Codeforces: contestId + index 형식. 예) 4A, 4/A';
  } else {
    problemIdInput.placeholder = '예) 1000';
    problemIdHelp.textContent = '백준: 숫자만 입력하세요. 예) 1000';
  }
}

platformSelect.addEventListener('change', syncProblemInputUI);
syncProblemInputUI();

const reviewBtn = document.getElementById('review-btn');
reviewBtn.dataset.label = '분석 시작';
reviewBtn.dataset.loadingLabel = '분석 중...';

// '자동 감지' 는 실패할 수 있다 — 어느 패턴에도 맞지 않는 코드와 드롭다운의 PyPy3 는
// detectLanguage 가 '' 를 돌려준다. 서버는 빈 언어를 400 으로
// 막는데(확장자가 .txt 로 떨어지면 재리뷰가 파일명을 재현하지 못해 영구 거부한다),
// 그 메시지가 "언어를 선택해주세요" 라 방금 '자동 감지' 를 고른 사용자에게는 말이 안 된다.
// 왕복 전에 정확한 이유로 안내한다.
const LANGUAGE_UNKNOWN_MSG = '코드에서 언어를 알아내지 못했습니다. 언어를 직접 선택해주세요.';

// 코드 에디터 + 언어 선택 값 — 리뷰 요청과 GitHub push 가 함께 쓴다.
function currentCodeAndLanguage() {
  const code = window.getEditorValue('code-input').trim();
  const langSelect = document.getElementById('code-language');
  return { code, language: (langSelect && langSelect.value) || detectLanguage(code) };
}

// 입력 폼 전체를 현재 값으로 읽어 요청 본문을 만든다 — 리뷰 요청과 대기 push 가 공유한다.
function currentReviewPayload() {
  const platform = platformSelect.value || 'boj';
  const problemId = document.getElementById('problem-id').value.trim();
  const problemStatement = document.getElementById('problem-statement').value.trim();
  const payload = {
    platform, ...currentCodeAndLanguage(),
    problem_statement: problemStatement || null,
  };
  if (platform === 'codeforces') payload.problem_ref = problemId;
  else payload.problem_id = Number(problemId);
  return payload;
}

reviewBtn.addEventListener('click', async () => {
  const problemId = document.getElementById('problem-id').value.trim();
  const result = document.getElementById('review-result');
  const payload = currentReviewPayload();

  if (!problemId) { showError(result, '문제 번호를 입력하세요.'); return; }
  if (!payload.code) { showError(result, '코드를 입력하세요.'); return; }
  if (!payload.language) { showError(result, LANGUAGE_UNKNOWN_MSG); return; }

  setLoading(reviewBtn, true);
  result.classList.remove('hidden');
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 코드를 분석 중입니다... (10~20초 소요)</div>';

  try {
    const data = await fetchJsonOk('/api/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, '분석 실패');
    renderReview(result, data);
  } catch (e) {
    // LLM 토큰이 없어 리뷰가 안 되는 경우가 있다 — 등록 자체가 막히지 않게 대기 push 경로를 준다.
    showError(result, e.message);
    renderPendingPushFallback(result);
  } finally {
    setLoading(reviewBtn, false);
  }
});

function renderPendingPushFallback(container) {
  const box = document.createElement('div');
  box.className = 'result-card';
  box.innerHTML = `
    <h4>리뷰 없이 먼저 올리기</h4>
    <p class="desc">
      AI 리뷰 없이 코드와 문제 정보만 GitHub에 올립니다. 위 입력값을 그대로 사용하므로
      문제 번호나 코드를 고쳤다면 고친 값으로 올라갑니다.
      나중에 '리뷰 기록' 탭에서 AI 리뷰를 실행하면 리뷰 기록과 README가 함께 갱신됩니다.
    </p>
    <div class="action-row">
      <button id="pending-push-btn" class="btn-primary btn-sm"
        data-label="리뷰 없이 GitHub에 올리기" data-loading-label="올리는 중...">
        리뷰 없이 GitHub에 올리기
      </button>
      <span id="pending-push-msg" class="action-msg"></span>
    </div>`;
  container.appendChild(box);

  document.getElementById('pending-push-btn').addEventListener('click', async () => {
    const btn = document.getElementById('pending-push-btn');
    const msg = document.getElementById('pending-push-msg');
    setLoading(btn, true);
    msg.textContent = '';
    msg.className = 'action-msg';
    // 입력값은 클릭 시점에 다시 읽는다 — 리뷰 실패 후 문제 번호나 코드를 고쳤을 수 있다.
    const pendingPayload = currentReviewPayload();
    if (!pendingPayload.language) {
      setLoading(btn, false);
      msg.textContent = LANGUAGE_UNKNOWN_MSG;
      msg.classList.add('bad');
      return;
    }
    try {
      const data = await fetchJsonOk('/api/review/pending', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pendingPayload),
      }, 'push 실패');
      btn.disabled = true;
      btn.textContent = '완료';
      msg.textContent = `${data.repo || ''}에 push 완료 (리뷰 대기)`;
      msg.classList.add('ok');
    } catch (e) {
      setLoading(btn, false);
      msg.textContent = e.message;
      msg.classList.add('bad');
    }
  });
}

function renderReview(container, d) {
  const tc = tierClass(d.tier);
  const tagsHtml = d.tags.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
  const strengthsHtml = (d.strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('') || '<li>-</li>';
  const weaknessesHtml = (d.weaknesses || []).map(w => `<li>${escapeHtml(w)}</li>`).join('') || '<li>-</li>';
  const feedbackHtml = renderMarkdown(d.feedback);
  const label = escapeHtml(problemLabel(d));
  const title = escapeHtml(d.title);
  const tierName = escapeHtml(d.tier_name);
  const betterAlgo = d.better_algorithm
    ? `<div class="summary-item"><div class="summary-label">더 나은 알고리즘</div><div class="summary-value summary-value-sm">${escapeHtml(d.better_algorithm)}</div></div>`
    : '';

  container.innerHTML = `
    <div class="result-card">
      <div class="problem-header">
        <span class="problem-title">
          <a href="${escapeHtml(problemUrl(d))}" target="_blank" rel="noopener noreferrer">
            ${label}. ${title}
          </a>
        </span>
        ${tierBadgeHtml(tc, tierName)}
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
        <div class="points-box good"><h4>잘한 점</h4><ul>${strengthsHtml}</ul></div>
        <div class="points-box bad"><h4>개선할 점</h4><ul>${weaknessesHtml}</ul></div>
      </div>
      <div class="feedback-box">
        <h4>상세 피드백</h4>
        <div class="markdown-body">${feedbackHtml}</div>
      </div>
      <div class="action-row">
        <button id="push-github-btn" class="btn-primary btn-sm"
          data-label="GitHub에 올리기" data-loading-label="올리는 중...">
          GitHub에 올리기
        </button>
        <span id="push-github-msg" class="action-msg"></span>
      </div>
    </div>
  `;

  document.getElementById('push-github-btn').addEventListener('click', async () => {
    const btn = document.getElementById('push-github-btn');
    const msg = document.getElementById('push-github-msg');
    const { code, language } = currentCodeAndLanguage();
    setLoading(btn, true);
    msg.textContent = '';
    msg.className = 'action-msg';
    try {
      const cfSections = _currentProblem?.ref === d.problem_ref ? _currentProblem.sections : null;
      const pastedStatement = document.getElementById('problem-statement')?.value?.trim() || '';
      const data = await fetchJsonOk('/api/push-review', {
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
          ...(d.platform === 'codeforces' ? {
            // 붙여넣은 본문이 먼저다 — 서버 resolve_statement 와 같은 우선순위여야
            // LLM 리뷰와 README 의 문제 설명이 갈리지 않는다. 뷰어를 닫아도
            // _currentProblem 이 남으므로, 뒤집으면 옛 번역본이 새 입력을 이긴다.
            description: pastedStatement || cfSections?.statement || '',
            input_desc: cfSections?.input || '',
            output_desc: cfSections?.output || '',
          } : {}),
        }),
      }, 'push 실패');
      btn.disabled = true;
      btn.textContent = '완료';
      msg.textContent = `${data.repo || ''}에 push 완료`;
      msg.classList.add('ok');
    } catch (e) {
      setLoading(btn, false);
      msg.textContent = e.message;
      msg.classList.add('bad');
    }
  });
}
