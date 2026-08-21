// 지난 제출을 편집 가능한 상태로 리뷰 폼에 채운다.
// 진입점 셋이 이 파일을 쓴다 — 메인 탭 버튼, 리뷰 기록 모달, ⌘K 팔레트.
// problem-modal.js 의 '코드 리뷰 진행' 도 fillReviewForm 위로 재작성됐다.

const loadSubmissionBtn = document.getElementById('load-submission-btn');
const loadSubmissionMsg = document.getElementById('load-submission-msg');

// DB 의 language 는 자유 문자열이다 — import 경로가 CF/BOJ 원문을 그대로 저장하므로
// "GNU G++17 7.3.0", "Python 3.8.10", "PyPy 3-64" 같은 값이 들어온다.
// select 에 없는 값을 대입하면 조용히 실패해 selectedIndex 가 -1(빈 select)이 된다.
function submissionLanguageOption(language, code) {
  const sel = document.getElementById('code-language');
  if (language && [...sel.options].some(o => o.value === language)) return language;
  // detectLanguage 의 반환값 도메인이 select 의 option value 와 같고, 제출할 때
  // review.js 도 같은 함수로 폴백한다 — 로더와 제출 경로의 판정이 어긋나지 않는다.
  return detectLanguage(code || '');
}

// 에디터에 편집 중인 코드가 있을 때만 확인한다.
function confirmEditorOverwrite() {
  if (!window.getEditorValue('code-input').trim()) return true;
  return confirm('에디터에 작성 중인 코드가 있습니다. 불러온 코드로 덮어쓸까요?');
}

function submissionSummary(review, seq, total) {
  const when = String(review.created_at || '').slice(0, 10);
  const parts = [];
  if (seq) parts.push(`${seq}회차${seq === total ? '(최신)' : ''}`);
  if (when) parts.push(when);
  parts.push(effLabel(review.efficiency));
  let msg = `${parts.join(' · ')} 코드를 불러왔습니다.`;
  if (total) msg += ` 수정 후 '분석 시작'을 누르면 ${total + 1}회차로 새로 기록됩니다.`;
  // 재리뷰는 최신 회차만 대상이라(routes/rereview.py) 대기 회차 위에 새 제출을 쌓으면
  // 그 회차는 영구히 대기로 남는다.
  if (review.efficiency === EFF_PENDING) {
    msg += ' 이 회차는 리뷰 대기 상태입니다 — 새로 제출하면 대기로 남으니'
        + " '리뷰 기록'에서 AI 리뷰를 먼저 실행하는 것을 권합니다.";
  }
  return msg;
}

// review = /api/reviews/problem/{platform}/{ref} 의 한 원소.
// seq/total 을 주면 몇 회차를 불러왔는지 안내한다.
function fillReviewForm(review, seq, total) {
  const platformSel = document.getElementById('problem-platform');
  platformSel.value = review.platform || 'boj';
  // change 를 직접 발생시켜야 review.js 가 placeholder·안내문을 갱신한다.
  platformSel.dispatchEvent(new Event('change'));

  // problemLabel 이 CF 는 problem_ref, BOJ 는 problem_id 를 준다 — 분기를 새로 쓰지 않는다.
  document.getElementById('problem-id').value = problemLabel(review);

  // 조건 없이 대입한다. resolve_statement 는 요청에 본문이 있으면 무조건 그것을 쓰므로,
  // 이전 문제의 붙여넣은 본문이 남으면 다른 문제를 그 본문으로 리뷰한다.
  const statement = document.getElementById('problem-statement');
  statement.value = review.problem_statement || '';
  document.getElementById('statement-toggle').open = Boolean(statement.value);

  const langSel = document.getElementById('code-language');
  langSel.value = submissionLanguageOption(review.language, review.code);
  // change 를 발생시켜야 editor.js 가 CodeMirror 모드와 자동완성 사전을 바꾼다.
  langSel.dispatchEvent(new Event('change'));

  window.setEditorValue('code-input', review.code || '');

  activateTab('review');
  window.scrollTo({ top: 0, behavior: 'smooth' });

  if (loadSubmissionMsg) {
    loadSubmissionMsg.className = 'hint';
    loadSubmissionMsg.textContent = seq ? submissionSummary(review, seq, total) : '';
    if (!langSel.value) {
      loadSubmissionMsg.textContent +=
        ' 언어 정보가 없어 자동 감지로 뒀습니다 — GitHub 업로드에는 언어 선택이 필요합니다.';
    }
  }
}

async function fetchLatestSubmission(platform, problemRef) {
  const data = await fetchJsonOk(
    `/api/reviews/problem/${encodeURIComponent(platform)}/${encodeURIComponent(problemRef)}`,
    undefined, '기록 조회 실패');
  const reviews = data.reviews || [];
  if (!reviews.length) throw new Error('이 문제의 리뷰 기록이 없습니다.');
  return { review: reviews[0], total: reviews.length };
}

if (loadSubmissionBtn) {
  loadSubmissionBtn.dataset.label = '지난 제출 불러오기';
  loadSubmissionBtn.dataset.loadingLabel = '불러오는 중...';

  loadSubmissionBtn.addEventListener('click', async () => {
    const platform = document.getElementById('problem-platform').value || 'boj';
    const problemRef = document.getElementById('problem-id').value.trim();
    loadSubmissionMsg.className = 'hint';
    loadSubmissionMsg.textContent = '';

    if (!problemRef) {
      loadSubmissionMsg.className = 'hint hint-bad';
      loadSubmissionMsg.textContent = '먼저 문제 번호를 입력하세요.';
      return;
    }
    if (!confirmEditorOverwrite()) return;

    setLoading(loadSubmissionBtn, true);
    try {
      const { review, total } = await fetchLatestSubmission(platform, problemRef);
      fillReviewForm(review, total, total);   // 최신 회차 = total 회차
    } catch (e) {
      loadSubmissionMsg.className = 'hint hint-bad';
      loadSubmissionMsg.textContent = e.message;
    } finally {
      setLoading(loadSubmissionBtn, false);
    }
  });
}
