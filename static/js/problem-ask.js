// 문제 뷰어 질문 — 열린 문제의 본문과 질문(앞선 대화 포함)을 /api/problem/ask 로 보내 답을 쌓는다.
// 대화는 문제를 열 때마다 새로 시작한다. 서버는 대화를 저장하지 않아 앞선 문답을 매번 함께 보낸다.

// 서버 상한(routes/models.py 의 MAX_ASK_TURNS·MAX_ANSWER_LENGTH)과 같다.
const ASK_HISTORY_TURNS = 5;
const ASK_ANSWER_MAX = 20000;
const ASK_SECTION_LABELS = { statement: '문제', input: '입력', output: '출력', note: '노트' };

// 대화가 속한 문제(problem-modal.js 의 _currentProblem 객체)와 그 문답 목록.
let _askProblem = null;
let _askTurns = [];

// openProblemModal 이 문제를 열 때 부른다. 본문이 뜨기 전에는 질문 칸을 숨긴다.
function resetProblemAsk(problem) {
  _askProblem = problem;
  _askTurns = [];
  document.getElementById('pm-ask').classList.add('hidden');
  document.getElementById('pm-ask-thread').innerHTML = '';
  document.getElementById('pm-ask-input').value = '';
  setLoading(document.getElementById('pm-ask-btn'), false);
}

// openProblemModal 이 본문을 그린 뒤 부른다.
function showProblemAsk() {
  document.getElementById('pm-ask').classList.remove('hidden');
}

// 뷰어가 받은 번역 본문을 텍스트 한 덩어리로. CF 는 섹션 + 예제(입력·출력), LeetCode 는 텍스트판
// 하나다 — LeetCode 예제는 입력만 있고 본문에 이미 실려 있어 붙이지 않는다.
function problemContextText(problem) {
  const parts = Object.entries(problem.sections || {})
    .filter(([, text]) => text)
    .map(([key, text]) => `### ${ASK_SECTION_LABELS[key] || key}\n${text}`);
  (problem.samples || []).forEach((sample, i) => {
    if (sample.output == null) return;
    parts.push(`### 예제 ${i + 1}\n입력:\n${sample.input}\n출력:\n${sample.output}`);
  });
  return parts.join('\n\n');
}

async function askAboutProblem() {
  const problem = _askProblem;
  const input = document.getElementById('pm-ask-input');
  const question = input.value.trim();
  if (!problem || !question) return;
  const btn = document.getElementById('pm-ask-btn');
  if (btn.disabled) return;

  const turnEl = document.createElement('div');
  turnEl.className = 'pm-ask-turn';
  turnEl.innerHTML = `
    <div class="pm-ask-q">${escapeHtml(question)}</div>
    <div class="pm-ask-a"><span class="spinner spinner-sm"></span> 답을 기다리는 중...</div>`;
  document.getElementById('pm-ask-thread').appendChild(turnEl);
  const answerEl = turnEl.querySelector('.pm-ask-a');
  setLoading(btn, true);

  try {
    const data = await fetchJsonOk('/api/problem/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        platform: problem.platform,
        problem_ref: problem.ref,
        title: problem.title || '',
        statement: problemContextText(problem),
        question,
        code: document.getElementById('pm-ask-with-code').checked ? window.getEditorValue('pm-code') : '',
        history: _askTurns.slice(-ASK_HISTORY_TURNS)
          .map(t => ({ question: t.question, answer: t.answer.slice(0, ASK_ANSWER_MAX) })),
      }),
    }, '질문 답변 실패');
    // 기다리는 사이 다른 문제를 열었으면 그 대화에 끼우지 않는다.
    if (_askProblem !== problem) return;
    _askTurns.push({ question, answer: data.answer });
    input.value = '';
    answerEl.innerHTML = `
      <div class="pm-ask-model">${escapeHtml(data.model)}</div>
      <div class="markdown-body">${renderMarkdown(data.answer)}</div>`;
    if (typeof renderMathInElement !== 'undefined') {
      renderMathInElement(answerEl, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
        ],
        throwOnError: false,
      });
    }
  } catch (e) {
    if (_askProblem !== problem) return;
    answerEl.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  } finally {
    if (_askProblem === problem) setLoading(btn, false);
  }
}

document.getElementById('pm-ask-btn').addEventListener('click', askAboutProblem);
document.getElementById('pm-ask-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    askAboutProblem();
  }
});
