const cfImportBtn = document.getElementById('cf-import-btn');
cfImportBtn.dataset.label = 'Codeforces에서 가져오기';

cfImportBtn.addEventListener('click', async () => {
  const handle = document.getElementById('cf-handle').value.trim();
  const count = Number(document.getElementById('cf-count').value);
  const apiKey = document.getElementById('cf-api-key').value.trim();
  const apiSecret = document.getElementById('cf-api-secret').value.trim();
  const result = document.getElementById('cf-import-result');

  if (!handle) { showError(result, 'Codeforces handle을 입력하세요.'); return; }

  setLoading(cfImportBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> Codeforces 제출 기록을 가져오는 중입니다...</div>';

  const ghRepo = (document.getElementById('cf-gh-repo')?.value || '').trim();
  const ghToken = (document.getElementById('cf-gh-token')?.value || '').trim();

  try {
    const data = await fetchJsonOk('/api/import-codeforces', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        handle, count,
        api_key: apiKey || null,
        api_secret: apiSecret || null,
        github_repo: ghRepo || null,
        github_token: ghToken || null,
      }),
    }, '가져오기 실패');

    const sourceMsg = data.has_source
      ? '<br><span class="hint">소스 코드 포함 항목이 있어 AI 리뷰까지 바로 이어갈 수 있습니다.</span>'
      : '<br><span class="hint">현재는 코드 없이 기록만 가져왔습니다. API Key/Secret을 넣으면 본인 계정 소스 코드도 함께 가져올 수 있습니다.</span>';

    const githubMsg = (data.github_pushed > 0)
      ? `<br><span class="hint-ok">GitHub <b>${escapeHtml(data.github_repo)}</b>에 <b>${data.github_pushed}</b>개 push 완료 (Codeforces/ 폴더)</span>`
      : '';

    result.innerHTML = `
      <div class="alert alert-ok">
        완료! <b>${escapeHtml(data.handle)}</b>의 Codeforces 기록 <b>${data.total_found}</b>개 확인 →
        <b>${data.imported}</b>개 새로 저장, <b>${data.skipped}</b>개 이미 있음
        ${sourceMsg}${githubMsg}
      </div>`;
    loadImportedHistory();
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(cfImportBtn, false);
  }
});
