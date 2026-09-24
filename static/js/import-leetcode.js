const lcImportBtn = document.getElementById('lc-import-btn');
lcImportBtn.dataset.label = 'LeetCode에서 가져오기';
lcImportBtn.dataset.loadingLabel = '가져오는 중...';

lcImportBtn.addEventListener('click', async () => {
  const username = document.getElementById('lc-username').value.trim();
  const count = Number(document.getElementById('lc-count').value);
  const session = document.getElementById('lc-session').value.trim();
  const result = document.getElementById('lc-import-result');

  if (!username) { showError(result, 'LeetCode 사용자 이름을 입력하세요.'); return; }

  setLoading(lcImportBtn, true);
  result.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> LeetCode 제출 기록을 가져오는 중입니다...</div>';

  const ghRepo = (document.getElementById('lc-gh-repo')?.value || '').trim();
  const ghToken = (document.getElementById('lc-gh-token')?.value || '').trim();

  try {
    const data = await fetchJsonOk('/api/import-leetcode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username, count,
        session: session || null,
        github_repo: ghRepo || null,
        github_token: ghToken || null,
      }),
    }, '가져오기 실패');

    const sourceMsg = data.has_source
      ? '<br><span class="hint">소스 코드 포함 항목이 있어 AI 리뷰까지 바로 이어갈 수 있습니다.</span>'
      : '<br><span class="hint">현재는 코드 없이 최근 AC 목록만 가져왔습니다. '
        + 'LEETCODE_SESSION 쿠키를 넣으면 본인 AC 코드까지 가져옵니다.</span>';

    const githubMsg = (data.github_pushed > 0)
      ? `<br><span class="hint-ok">GitHub <b>${escapeHtml(data.github_repo)}</b>에 `
        + `<b>${data.github_pushed}</b>개 push 완료 (LeetCode/ 폴더)</span>`
      : '';

    result.innerHTML = `
      <div class="alert alert-ok">
        완료! <b>${escapeHtml(data.username)}</b>의 LeetCode 기록 <b>${data.total_found}</b>개 확인 →
        <b>${data.imported}</b>개 새로 저장, <b>${data.skipped}</b>개 이미 있음
        ${sourceMsg}${githubMsg}
      </div>`;
    loadImportedHistory();
  } catch (e) {
    showError(result, e.message);
  } finally {
    setLoading(lcImportBtn, false);
  }
});
