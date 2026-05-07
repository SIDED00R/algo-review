/* 종합 리포트 탭 — 리포트 생성 요청 및 마크다운 렌더링만 담당 */

const reportBtn = document.getElementById('report-btn');
reportBtn.dataset.label = '리포트 생성';

reportBtn.addEventListener('click', async () => {
  const result = document.getElementById('report-result');
  setLoading(reportBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 종합 분석 중입니다... (10~20초 소요)</div>';

  try {
    const res = await fetch('/api/report');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '실패');
    result.innerHTML = `
      <div class="result-card">
        <div class="feedback-box">
          <h4>📊 종합 분석 리포트</h4>
          <div class="markdown-body">${DOMPurify.sanitize(marked.parse(data.report))}</div>
        </div>
      </div>`;
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(reportBtn, false);
  }
});
