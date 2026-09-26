// LeetCode 채점기 경로 — 뷰어의 예제 실행(/api/leetcode/run)과 제출(/api/leetcode/submit).
// problem-modal.js 의 _currentProblem·_runToken·resetRunButton·setReviewOutcome 을 공유한다.
// 예제는 CF 처럼 케이스마다 요청하지 않고 한 번에 보낸다 — 채점기가 케이스별 결과를 준다.

function lcCaseLabel(index, builtinCount) {
  return index < builtinCount ? `테스트 ${index + 1}` : `커스텀 ${index - builtinCount + 1}`;
}

function renderLeetcodeRun(result, builtinCount) {
  if (!result.run_success) {
    // 컴파일 오류·런타임 오류는 케이스별 결과가 없다 — 상태와 오류 원문만 보인다.
    return `
      <div class="test-case fail">
        <span class="tc-badge">${escapeHtml(result.status_msg || '실패')}</span>
        <div class="tc-detail"><pre>${escapeHtml(result.error || '(상세 없음)')}</pre></div>
      </div>`;
  }
  const cases = result.cases.map((c, i) => {
    const detail = c.passed ? '' : `
      <div class="tc-detail">
        <div><b>입력</b><pre>${escapeHtml(c.input)}</pre></div>
        <div><b>예상 출력</b><pre>${escapeHtml(c.expected)}</pre></div>
        <div><b>실제 출력</b><pre>${escapeHtml(c.actual || '(없음)')}</pre></div>
      </div>`;
    return `
      <div class="test-case ${c.passed ? 'pass' : 'fail'}">
        <span class="tc-badge">${c.passed ? '통과' : '실패'}</span>${lcCaseLabel(i, builtinCount)}
        ${detail}
      </div>`;
  }).join('');
  const runtime = result.runtime ? `<p class="hint">LeetCode 채점기 · ${escapeHtml(result.runtime)}</p>` : '';
  return cases + runtime;
}

async function runLeetcodeSamples(allCases, code, language) {
  const resultsEl = document.getElementById('pm-test-results');
  const btn = document.getElementById('pm-run-btn');
  const builtinCount = allCases.filter(c => !c.isCustom).length;

  btn.disabled = true;
  btn.textContent = '실행 중...';
  // 반대편 버튼도 잠근다 — 진행 중에 누르면 세대 토큰이 바뀌어 먼저 보낸 요청의 결과가 버려진다.
  document.getElementById('pm-submit-btn').disabled = true;
  resultsEl.innerHTML =
    '<div class="test-case pending"><span class="spinner spinner-sm"></span> LeetCode 채점기에서 실행 중...</div>';
  setReviewOutcome(true);

  // 요청 중 모달을 닫거나 다른 문제를 열면 세대가 바뀐다 — 늦은 응답을 그리지 않는다.
  const runToken = ++_runToken;
  let allPassed = false;
  try {
    const result = await fetchJsonOk('/api/leetcode/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        problem_ref: _currentProblem.ref, language, code, cases: allCases.map(c => c.input),
      }),
    }, '예제 실행 실패');
    if (runToken !== _runToken) return;
    allPassed = result.run_success && result.cases.every(c => c.passed);
    resultsEl.innerHTML = renderLeetcodeRun(result, builtinCount);
  } catch (e) {
    if (runToken !== _runToken) return;
    resultsEl.innerHTML =
      `<div class="test-case fail"><span class="tc-badge">실패</span> 오류: ${escapeHtml(e.message)}</div>`;
  } finally {
    if (runToken === _runToken) resetRunButton();
  }
  setReviewOutcome(allPassed);
}

function renderLeetcodeSubmit(result) {
  const link = `<a href="${escapeHtml(result.url)}" target="_blank" rel="noopener noreferrer">제출 기록 보기</a>`;
  const score = result.total_testcases != null
    ? `${result.total_correct ?? 0}/${result.total_testcases} 케이스` : '';
  const perf = [result.runtime, result.memory].filter(Boolean).map(escapeHtml).join(' · ');
  if (result.accepted) {
    return `
      <div class="test-case pass">
        <span class="tc-badge">Accepted</span>${score}
        <span class="tc-time">${perf}</span> ${link}
      </div>`;
  }
  // 오답이면 첫 실패 케이스, 오류면 오류 원문.
  const detail = result.error ? `<pre>${escapeHtml(result.error)}</pre>` : `
    <div><b>입력</b><pre>${escapeHtml(result.last_testcase || '(없음)')}</pre></div>
    <div><b>예상 출력</b><pre>${escapeHtml(result.expected_output || '(없음)')}</pre></div>
    <div><b>실제 출력</b><pre>${escapeHtml(result.code_output || '(없음)')}</pre></div>`;
  return `
    <div class="test-case fail">
      <span class="tc-badge">${escapeHtml(result.status_msg || '실패')}</span>${score} ${link}
      <div class="tc-detail">${detail}</div>
    </div>`;
}

async function submitToLeetcode() {
  if (_currentProblem?.judge !== 'leetcode') return;
  const raw = window.getEditorValue('pm-code');
  const code = raw.trim();
  const resultsEl = document.getElementById('pm-test-results');
  // 손대지 않은 기본 코드 스텁도 막는다. 예제 실행은 막지 않는다.
  if (!code || raw === _currentProblem.appliedSnippet) {
    resultsEl.innerHTML = '<div class="alert alert-info">코드를 먼저 작성해주세요.</div>';
    return;
  }
  const language = document.getElementById('pm-language').value;
  const btn = document.getElementById('pm-submit-btn');
  btn.disabled = true;
  btn.textContent = '제출 중...';
  document.getElementById('pm-run-btn').disabled = true;
  resultsEl.innerHTML =
    '<div class="test-case pending"><span class="spinner spinner-sm"></span> LeetCode 에 제출 중...</div>';
  // 제출 판정이 예제 판정을 대신한다 — 앞선 예제 실패 문구를 Accepted 가 지운다.
  setReviewOutcome(true);

  const runToken = ++_runToken;
  try {
    const result = await fetchJsonOk('/api/leetcode/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ problem_ref: _currentProblem.ref, language, code }),
    }, '제출 실패');
    if (runToken !== _runToken) return;
    resultsEl.innerHTML = renderLeetcodeSubmit(result);
    setReviewOutcome(result.accepted);
  } catch (e) {
    if (runToken !== _runToken) return;
    resultsEl.innerHTML =
      `<div class="test-case fail"><span class="tc-badge">실패</span> 오류: ${escapeHtml(e.message)}</div>`;
  } finally {
    if (runToken === _runToken) resetRunButton();
  }
}

document.getElementById('pm-submit-btn').addEventListener('click', submitToLeetcode);
