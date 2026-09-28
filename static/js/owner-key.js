// 소유자 열쇠 등록 — `/#owner=<열쇠>` 로 열면 서버에 보내 HttpOnly 쿠키로 심는다.
// 해시는 서버로 전송되지 않아 요청 로그에 남지 않는다. 읽은 즉시 주소창에서 지운다.
(function () {
  const match = location.hash.match(/^#owner=(.+)$/);
  if (!match) return;
  history.replaceState({}, '', location.pathname + location.search);
  fetchJsonOk('/api/owner/key', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: match[1] }),
  }, '열쇠를 등록하지 못했습니다.')
    .then(() => alert('이 브라우저의 요청은 이제 Claude 구독으로 답합니다.'))
    .catch(e => alert(e.message));
})();
