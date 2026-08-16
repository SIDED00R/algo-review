function showDisconnectedGithubUI(iconBtn, statusBadge, connectInner) {
  iconBtn.classList.remove('connected');
  iconBtn.title = 'GitHub 연결';
  statusBadge.style.display = 'none';
  connectInner.style.display = 'block';
}

async function loadGithubStatus() {
  const iconBtn = document.getElementById('github-icon-btn');
  const statusBadge = document.getElementById('github-status-badge');
  const connectInner = document.getElementById('github-connect-inner');
  try {
    const res = await fetch('/auth/github/status');
    const data = await res.json();
    const usernameBadge = document.getElementById('github-username-badge');
    const repoSelect = document.getElementById('github-repo-select');

    if (data.connected) {
      iconBtn.classList.add('connected');
      iconBtn.title = `GitHub: @${data.username}`;
      statusBadge.style.display = 'block';
      connectInner.style.display = 'none';
      usernameBadge.textContent = `@${data.username}`;

      try {
        const repoRes = await fetch('/auth/github/repos');
        const repoData = await repoRes.json();
        repoSelect.innerHTML = '<option value="">저장소 선택...</option>' +
          (repoData.repos || []).map(r =>
            `<option value="${r.full_name}" ${r.full_name === data.target_repo ? 'selected' : ''}>${r.full_name}${r.private ? ' 🔒' : ''}</option>`
          ).join('');
      } catch {}

      repoSelect.addEventListener('change', async () => {
        const repo = repoSelect.value;
        if (!repo) return;
        await fetch('/auth/github/repo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo }),
        });
      });
    } else {
      showDisconnectedGithubUI(iconBtn, statusBadge, connectInner);
    }
  } catch {
    showDisconnectedGithubUI(iconBtn, statusBadge, connectInner);
  }
}

document.getElementById('github-icon-btn')?.addEventListener('click', (e) => {
  e.stopPropagation();
  const dropdown = document.getElementById('github-dropdown');
  dropdown.classList.toggle('hidden');
});

document.addEventListener('click', (e) => {
  const wrap = document.querySelector('.github-wrap');
  if (wrap && !wrap.contains(e.target)) {
    document.getElementById('github-dropdown')?.classList.add('hidden');
  }
});

document.getElementById('github-connect-btn')?.addEventListener('click', () => {
  window.location.href = '/auth/github';
});

document.getElementById('github-disconnect-btn')?.addEventListener('click', async () => {
  if (!confirm('GitHub 연결을 해제하시겠습니까?')) return;
  await fetch('/auth/github', { method: 'DELETE' });
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
