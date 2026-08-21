const ghImportBtn = document.getElementById('gh-import-btn');
ghImportBtn.dataset.label = 'GitHub에서 가져오기';
ghImportBtn.dataset.loadingLabel = '가져오는 중...';

ghImportBtn.addEventListener('click', async () => {
  const repo = document.getElementById('gh-repo').value.trim();
  const token = document.getElementById('gh-token').value.trim();
  const result = document.getElementById('gh-import-result');

  if (!repo) { showError(result, 'GitHub 저장소 주소를 입력하세요.'); return; }

  setLoading(ghImportBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> GitHub에서 파일 목록을 가져오는 중...</div>';

  try {
    const data = await fetchJsonOk('/api/import-github', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo, token: token || null }),
    }, '실패');

    const failMsg = data.failed && data.failed.length > 0
      ? `<br><span class="hint">정보 조회 실패: ${data.failed.length}개</span>`
      : '';
    result.innerHTML = `
      <div class="alert alert-ok">
        완료! 저장소에서 <b>${data.total_found}</b>개 발견 →
        <b>${data.imported}</b>개 새로 저장, <b>${data.skipped}</b>개 이미 있음${failMsg}
      </div>
      <button id="gh-reimport-btn" class="btn-secondary btn-danger">
        기존 기록 전체 삭제 후 다시 가져오기
      </button>`;
    document.getElementById('gh-reimport-btn').addEventListener('click', async () => {
      if (!confirm('가져온 기록을 전부 삭제하고 다시 가져옵니다. 계속할까요?')) return;
      await fetch('/api/solved-history', { method: 'DELETE' });
      ghImportBtn.click();
    });
    loadImportedHistory();
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(ghImportBtn, false);
  }
});
