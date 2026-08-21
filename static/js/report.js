const reportBtn = document.getElementById('report-btn');
reportBtn.dataset.label = '리포트 생성';
reportBtn.dataset.loadingLabel = '리포트 생성 중...';

let selectedReportPlatform = 'boj';
document.querySelectorAll('[data-report-platform]').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.reportPlatform === selectedReportPlatform) return;
    selectedReportPlatform = btn.dataset.reportPlatform;
    document.querySelectorAll('[data-report-platform]').forEach(b => {
      const on = b === btn;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', String(on));
    });
  });
});

// 요청 세대 토큰 — 플랫폼을 바꿔 연속 생성하면 늦게 온 이전 플랫폼 응답이 새 결과를 덮는다.
let _reportToken = 0;

reportBtn.addEventListener('click', async () => {
  const result = document.getElementById('report-result');
  const token = ++_reportToken;
  setLoading(reportBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> 종합 분석 중입니다... (10~20초 소요)</div>';

  try {
    const data = await fetchJsonOk(`/api/report?platform=${selectedReportPlatform}`, undefined, '실패');
    if (token !== _reportToken) return;
    result.innerHTML = `
      <div class="result-card">
        <div class="feedback-box">
          <h4>📊 종합 분석 리포트</h4>
          <div class="markdown-body">${renderMarkdown(data.report)}</div>
        </div>
      </div>`;
  } catch (e) {
    if (token !== _reportToken) return;
    showError(result, e.message);
  } finally {
    if (token === _reportToken) setLoading(reportBtn, false);
  }
});
