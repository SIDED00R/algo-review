function showDisconnectedGithubUI(iconBtn, statusBadge, connectInner) {
  iconBtn.classList.remove('connected');
  iconBtn.setAttribute('aria-label', 'GitHub 연결');
  statusBadge.classList.add('hidden');
  connectInner.classList.remove('hidden');
}

async function loadGithubStatus() {
  const iconBtn = document.getElementById('github-icon-btn');
  const statusBadge = document.getElementById('github-status-badge');
  const connectInner = document.getElementById('github-connect-inner');
  try {
    // fetchJsonOk 를 쓴다 — res.ok 를 안 보면 503(온디맨드 DB 정지)의 {"detail":...} 에서
    // data.connected 가 undefined 가 되어 "연결 해제" 로 보인다. 사용자는 연결이 끊긴 줄
    // 알고 재연결을 시도한다.
    const data = await fetchJsonOk('/auth/github/status', undefined, 'GitHub 상태 조회 실패');
    const usernameBadge = document.getElementById('github-username-badge');
    const repoSelect = document.getElementById('github-repo-select');

    if (data.connected) {
      iconBtn.classList.add('connected');
      iconBtn.setAttribute('aria-label', `GitHub: @${data.username}`);
      statusBadge.classList.remove('hidden');
      connectInner.classList.add('hidden');
      usernameBadge.textContent = `@${data.username}`;

      try {
        const repoData = await fetchJsonOk('/auth/github/repos', undefined, '저장소 목록 로딩 실패');
        repoSelect.innerHTML = '<option value="">저장소 선택...</option>' +
          (repoData.repos || []).map(r =>
            `<option value="${escapeHtml(r.full_name)}" ${r.full_name === data.target_repo ? 'selected' : ''}>${escapeHtml(r.full_name)}${r.private ? ' (비공개)' : ''}</option>`
          ).join('');
      } catch (e) {
        // 예전에는 catch {} 로 삼켜 빈 select 만 남았다 — 사용자는 원인을 알 수 없다.
        repoSelect.innerHTML = `<option value="">${escapeHtml(e.message)}</option>`;
      }

      if (!repoSelect.dataset.bound) {
        // 데이터 로딩 함수 안에서 리스너를 걸면 재호출 시 누적된다.
        repoSelect.dataset.bound = '1';
        repoSelect.addEventListener('change', async () => {
          const repo = repoSelect.value;
          if (!repo) return;
          const msg = document.getElementById('github-repo-msg');
          try {
            await fetchJsonOk('/auth/github/repo', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ repo }),
            }, '저장소 변경 실패');
            if (msg) { msg.textContent = '저장소를 저장했습니다.'; msg.className = 'action-msg ok'; }
          } catch (e) {
            // 예전에는 응답을 확인하지 않아 변경 실패가 무음이었다.
            if (msg) { msg.textContent = e.message; msg.className = 'action-msg bad'; }
          }
        });
      }
    } else {
      showDisconnectedGithubUI(iconBtn, statusBadge, connectInner);
    }
  } catch {
    showDisconnectedGithubUI(iconBtn, statusBadge, connectInner);
  }
}

function setGithubDropdown(open) {
  document.getElementById('github-dropdown')?.classList.toggle('hidden', !open);
  document.getElementById('github-icon-btn')?.setAttribute('aria-expanded', String(open));
}

document.getElementById('github-icon-btn')?.addEventListener('click', (e) => {
  e.stopPropagation();
  const dropdown = document.getElementById('github-dropdown');
  setGithubDropdown(dropdown.classList.contains('hidden'));
});

document.addEventListener('click', (e) => {
  const wrap = document.querySelector('.github-wrap');
  if (wrap && !wrap.contains(e.target)) setGithubDropdown(false);
});

document.getElementById('github-connect-btn')?.addEventListener('click', () => {
  window.location.href = '/auth/github';
});

document.getElementById('github-disconnect-btn')?.addEventListener('click', async () => {
  if (!confirm('GitHub 연결을 해제하시겠습니까?')) return;
  try {
    await fetchJsonOk('/auth/github', { method: 'DELETE' }, '연결 해제 실패');
  } catch (e) {
    const msg = document.getElementById('github-repo-msg');
    if (msg) { msg.textContent = e.message; msg.className = 'action-msg bad'; }
    return;   // 실패했는데 새로고침하면 해제된 것처럼 보인다
  }
  location.reload();
});

(function () {
  const params = new URLSearchParams(location.search);
  if (params.get('github') === 'connected') {
    history.replaceState({}, '', '/');
  } else if (params.get('github') === 'error') {
    alert('GitHub 연결에 실패했습니다. 다시 시도해주세요.');
    history.replaceState({}, '', '/');
  }
})();

loadGithubStatus();
