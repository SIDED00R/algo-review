function outputMatches(actual, expected) {
  if (actual === expected) return true;
  const aLines = actual.split('\n');
  const eLines = expected.split('\n');
  if (aLines.length !== eLines.length) return false;
  return aLines.every((a, i) => {
    const e = eLines[i];
    if (a.trimEnd() === e.trimEnd()) return true;
    const dec = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;
    const at = a.trim(), et = e.trim();
    return dec.test(at) && dec.test(et) &&
      Math.abs(parseFloat(at) - parseFloat(et)) < 1e-6;
  });
}

let _currentProblem = null;

async function openProblemModal(ref, title, tierName) {
  _currentProblem = { ref, samples: [] };

  const modal = document.getElementById('problem-modal');
  modal.classList.remove('hidden');
  document.getElementById('pm-title').textContent = `${ref}. ${title}`;
  document.getElementById('pm-difficulty').textContent = tierName;
  document.getElementById('pm-meta').textContent = '';
  document.getElementById('pm-link').innerHTML = '';
  document.getElementById('pm-loading').classList.remove('hidden');
  document.getElementById('pm-loading').innerHTML = '<span class="spinner"></span> 문제 불러오는 중...';
  document.getElementById('pm-statement').classList.add('hidden');
  document.getElementById('pm-statement').innerHTML = '';
  document.getElementById('pm-test-results').innerHTML = '';
  document.getElementById('pm-custom-cases').innerHTML = '';
  _customCaseCount = 0;
  const _rb = document.getElementById('pm-review-btn');
  _rb.classList.add('hidden');
  _rb.textContent = '코드 리뷰 진행 →';
  _rb.title = '';
  window.setEditorValue('pm-code', '');

  try {
    const res = await fetch(`/api/problem/cf/${ref}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '문제 로딩 실패');

    _currentProblem.samples  = data.samples;
    _currentProblem.sections = data.statement_sections_ko || {};

    document.getElementById('pm-title').textContent = `${ref}. ${data.title}`;
    document.getElementById('pm-meta').textContent = `${data.time_limit} · ${data.memory_limit}`;
    const pUrl = data.url || cfRefToUrl(ref);
    document.getElementById('pm-link').innerHTML = pUrl
      ? `<a href="${escapeHtml(pUrl)}" target="_blank" rel="noopener noreferrer">문제 링크 열기</a>`
      : '';
    document.getElementById('pm-loading').classList.add('hidden');

    const samplesHtml = data.samples.map((s, i) => `
      <div class="pm-sample">
        <div class="pm-sample-title">예제 입력 ${i + 1}</div>
        <pre class="pm-pre">${escapeHtml(s.input)}</pre>
        <div class="pm-sample-title">예제 출력 ${i + 1}</div>
        <pre class="pm-pre">${escapeHtml(s.output)}</pre>
      </div>`).join('');

    const sections = data.statement_sections_ko || {};
    const sectionDefs = [
      { key: 'statement', label: '문제' },
      { key: 'input',     label: '입력' },
      { key: 'output',    label: '출력' },
      { key: 'note',      label: '노트' },
    ];
    const sectionsHtml = sectionDefs
      .filter(({ key }) => sections[key])
      .map(({ key, label }) => {
        const parts = sections[key].split(/(\$\$[\s\S]*?\$\$|\$[^$\n]+?\$)/);
        const escaped = parts.map((part, i) => {
          if (i % 2 === 1) return part;
          let text = part;
          if (i > 0) text = text.replace(/^\n+/, '');
          if (i < parts.length - 1) text = text.replace(/\n+$/, '');
          return escapeHtml(text).replace(/\n/g, '<br>');
        }).join('');
        return `
        <div class="pm-section-card">
          <h3>${label}</h3>
          <div class="pm-text">${escaped}</div>
        </div>`;
      })
      .join('');

    const stmtEl = document.getElementById('pm-statement');
    stmtEl.innerHTML = sectionsHtml + samplesHtml;
    stmtEl.classList.remove('hidden');
    if (typeof renderMathInElement !== 'undefined') {
      renderMathInElement(stmtEl, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
        ],
        throwOnError: false,
      });
    }
  } catch (e) {
    document.getElementById('pm-loading').innerHTML =
      `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}

function closeProblemModal() {
  document.getElementById('problem-modal').classList.add('hidden');
}

let _customCaseCount = 0;

function addCustomCase() {
  const id = ++_customCaseCount;
  const el = document.createElement('div');
  el.className = 'pm-custom-case';
  el.id = `pm-custom-${id}`;
  el.innerHTML = `
    <div class="pm-custom-case-row">
      <div>
        <label>입력</label>
        <textarea id="pm-custom-input-${id}" placeholder="입력값을 입력하세요"></textarea>
      </div>
      <div>
        <label>기대 출력</label>
        <textarea id="pm-custom-output-${id}" placeholder="기대 출력값을 입력하세요"></textarea>
      </div>
    </div>
    <div class="pm-custom-case-footer">
      <button class="pm-custom-delete-btn" onclick="removeCustomCase(${id})">삭제</button>
    </div>`;
  document.getElementById('pm-custom-cases').appendChild(el);
}

function removeCustomCase(id) {
  document.getElementById(`pm-custom-${id}`)?.remove();
}

function getCustomCases() {
  return [...document.querySelectorAll('.pm-custom-case')].map(el => {
    const idMatch = el.id.match(/pm-custom-(\d+)/);
    if (!idMatch) return null;
    const id = idMatch[1];
    return {
      input: document.getElementById(`pm-custom-input-${id}`)?.value ?? '',
      output: document.getElementById(`pm-custom-output-${id}`)?.value ?? '',
    };
  }).filter(Boolean);
}

async function runSamples() {
  const builtinSamples = _currentProblem?.samples || [];
  const customCases = getCustomCases();
  const allCases = [
    ...builtinSamples.map(s => ({ ...s, isCustom: false })),
    ...customCases.map(s => ({ input: s.input, output: s.output, isCustom: true })),
  ];

  const code = window.getEditorValue('pm-code').trim();
  const resultsEl = document.getElementById('pm-test-results');

  if (!code) {
    resultsEl.innerHTML = '<div class="alert alert-info">코드를 먼저 작성해주세요.</div>';
    return;
  }
  if (!allCases.length) {
    resultsEl.innerHTML = '<div class="alert alert-info">예제 데이터가 없습니다.</div>';
    return;
  }

  const language = document.getElementById('pm-language').value;
  const btn = document.getElementById('pm-run-btn');

  btn.disabled = true;
  btn.textContent = '실행 중...';
  resultsEl.innerHTML = '';
  document.getElementById('pm-review-btn').classList.add('hidden');

  let allPassed = true;

  for (let i = 0; i < allCases.length; i++) {
    const sample = allCases[i];
    const tcId = `tc-${i}`;
    const label = sample.isCustom ? `커스텀 ${i - builtinSamples.length + 1}` : `테스트 ${i + 1}`;
    resultsEl.innerHTML += `<div class="test-case pending" id="${tcId}"><span class="spinner" style="width:14px;height:14px;border-width:2px"></span> ${label} 실행 중...</div>`;

    try {
      const res = await fetch('/api/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language, stdin: sample.input, timeout_sec: 5 }),
      });
      const result = await res.json();

      const actual = (result.stdout || '').trimEnd();
      const expected = sample.output.trimEnd();
      const passed = outputMatches(actual, expected) && result.exit_code === 0;
      if (!passed) allPassed = false;

      const detailHtml = !passed ? `
        <div class="tc-detail">
          <div><b>입력</b><pre>${escapeHtml(sample.input)}</pre></div>
          <div><b>예상 출력</b><pre>${escapeHtml(expected)}</pre></div>
          <div><b>실제 출력</b><pre>${escapeHtml(actual || result.stderr || '(없음)')}</pre></div>
        </div>` : '';

      document.getElementById(tcId).outerHTML = `
        <div class="test-case ${passed ? 'pass' : 'fail'}">
          <span class="tc-badge">${passed ? '✅ 통과' : '❌ 실패'}</span>${label}
          <span style="color:var(--text-muted);font-size:.78rem;margin-left:8px">${result.time_ms}ms</span>
          ${detailHtml}
        </div>`;
    } catch (e) {
      allPassed = false;
      document.getElementById(tcId).outerHTML =
        `<div class="test-case fail"><span class="tc-badge">❌</span>${label} — 오류: ${escapeHtml(e.message)}</div>`;
    }
  }

  btn.disabled = false;
  btn.textContent = '▶ 예제 실행';

  const reviewBtn = document.getElementById('pm-review-btn');
  reviewBtn.classList.remove('hidden');
  if (allPassed) {
    reviewBtn.textContent = '코드 리뷰 진행 →';
    reviewBtn.title = '';
  } else {
    reviewBtn.textContent = '⚠️ 예제 실패 — 그래도 리뷰 진행';
    reviewBtn.title = '일부 예제가 통과되지 않았습니다. 다중 정답 문제라면 진행해도 됩니다.';
  }
}

function proceedToReview() {
  if (!_currentProblem) return;

  document.getElementById('problem-platform').value = 'codeforces';
  document.getElementById('problem-platform').dispatchEvent(new Event('change'));
  document.getElementById('problem-id').value = _currentProblem.ref;
  window.setEditorValue('code-input', window.getEditorValue('pm-code'));

  const lang = document.getElementById('pm-language').value;
  document.getElementById('code-language').value = lang === 'cpp' ? 'GNU C++17' : 'Python 3';

  closeProblemModal();

  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(s => {
    s.classList.remove('active');
    s.classList.add('hidden');
  });
  document.querySelector('[data-tab="review"]').classList.add('active');
  const reviewTab = document.getElementById('tab-review');
  reviewTab.classList.remove('hidden');
  reviewTab.classList.add('active');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}
