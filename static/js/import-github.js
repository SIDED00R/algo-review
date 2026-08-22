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
      // 삭제 범위를 정확히 알린다 — DELETE /api/solved-history 는 플랫폼 구분 없이
      // 전 행을 지우는데 재수입은 GitHub 저장소 경로뿐이라, BOJ·Codeforces 로 직접
      // 가져온 기록은 복구 경로 없이 사라진다.
      if (!confirm('가져온 기록을 전부 삭제하고 GitHub 저장소에서 다시 가져옵니다. ' +
                   'BOJ·Codeforces 에서 직접 가져온 기록도 함께 삭제되며, ' +
                   '그쪽은 다시 가져오기를 따로 실행해야 합니다. 계속할까요?')) return;
      try {
        // 응답을 확인한다 — 확인하지 않으면 데모(403)나 DB 정지(503)에서 삭제가 실패해도
        // 그대로 재수입이 진행되어 "전체 삭제" 계약이 조용히 깨진다.
        await fetchJsonOk('/api/solved-history', { method: 'DELETE' }, '기록 삭제 실패');
      } catch (e) {
        showError(result, e.message);
        return;
      }
      ghImportBtn.click();
    });
    loadImportedHistory();
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(ghImportBtn, false);
  }
});
