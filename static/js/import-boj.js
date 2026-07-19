const importBtn = document.getElementById('import-btn');
importBtn.dataset.label = '가져오기';

importBtn.addEventListener('click', async () => {
  const bojId = document.getElementById('import-boj-id').value.trim();
  const cookie = document.getElementById('import-cookie').value.trim();
  const pages = Number(document.getElementById('import-pages').value);
  const result = document.getElementById('import-result');

  if (!bojId) { showError(result, 'BOJ 아이디를 입력하세요.'); return; }

  setLoading(importBtn, true);
  const pageDesc = pages >= 9999 ? '전체' : `최대 ${pages * 20}개`;
  result.innerHTML = `<div class="alert alert-info"><span class="spinner"></span> 제출 기록을 가져오는 중입니다... (${pageDesc}, 기록이 많으면 수 분 소요)</div>`;

  try {
    const data = await fetchJsonOk('/api/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ boj_id: bojId, session_cookie: cookie || null, max_pages: pages }),
    }, '가져오기 실패');

    const failMsg = data.failed && data.failed.length > 0
      ? `<br><span style="color:var(--text-muted);font-size:.82rem">정보 조회 실패: ${data.failed.join(', ')}</span>`
      : '';
    const bojGithubMsg = (data.github_pushed > 0)
      ? `<br><span style="color:var(--green);font-size:.82rem">🐙 GitHub <b>${data.github_repo}</b>에 <b>${data.github_pushed}</b>개 push 완료 (BOJ/ 폴더)</span>`
      : '';
    result.innerHTML = `
      <div class="alert alert-info" style="color:var(--green)">
        ✅ 완료! 총 <b>${data.total_found}</b>개 발견 →
        <b>${data.imported}</b>개 새로 저장, <b>${data.skipped}</b>개 이미 있음${failMsg}${bojGithubMsg}
      </div>`;
    loadImportedHistory();
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(importBtn, false);
  }
});
