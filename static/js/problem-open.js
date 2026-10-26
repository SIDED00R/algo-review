// 문제 직접 열기 — 추천 탭 상단 카드. 입력(번호·slug·URL)을 서버(/api/problem/lookup)가 정규 ref 와
// 제목·난이도로 풀어 주면 추천 카드와 같은 openProblemModal 로 뷰어를 연다. 입력값을 그대로 ref 로 쓰면
// 임시 저장 키·LeetCode 채점기·push 본문 매칭이 어긋난다. BOJ 는 뷰어가 없어 select 에 없다.
const openProblemPlatform = document.getElementById('open-problem-platform');
const openProblemRef = document.getElementById('open-problem-ref');
const openProblemHelp = document.getElementById('open-problem-help');
const openProblemBtn = document.getElementById('open-problem-btn');
const openProblemMsg = document.getElementById('open-problem-msg');
openProblemBtn.dataset.label = '뷰어로 열기';
openProblemBtn.dataset.loadingLabel = '문제 찾는 중...';

// 플랫폼에 맞는 입력 규약 안내 — 코드 리뷰 탭(review.js)과 같은 플랫폼 표를 읽는다.
function syncOpenProblemInputUI() {
  const spec = platformSpec(openProblemPlatform.value);
  openProblemRef.placeholder = spec.placeholder;
  openProblemHelp.textContent = spec.help;
}

// 조회 세대 — 입력칸 Enter 는 버튼 disabled 와 무관하게 조회를 다시 시작한다. 늦게 온 이전 응답이
// 새 문제를 덮는다(모달이 다시 열리며 에디터가 비워진다).
let _openProblemToken = 0;

async function openProblemByRef() {
  const platform = openProblemPlatform.value;
  const ref = openProblemRef.value.trim();
  openProblemMsg.textContent = '';
  if (!ref) {
    openProblemMsg.textContent = '문제 번호를 입력하세요.';
    openProblemRef.focus();
    return;
  }
  const token = ++_openProblemToken;
  setLoading(openProblemBtn, true);
  try {
    const params = new URLSearchParams({ platform, ref });
    const info = await fetchJsonOk(`/api/problem/lookup?${params}`, undefined, '문제 조회 실패');
    if (token !== _openProblemToken) return;
    openProblemModal(info.platform, info.problem_ref, info.title, info.tier_name);
  } catch (e) {
    if (token !== _openProblemToken) return;
    openProblemMsg.textContent = e.message;
  } finally {
    if (token === _openProblemToken) setLoading(openProblemBtn, false);
  }
}

openProblemPlatform.addEventListener('change', syncOpenProblemInputUI);
openProblemBtn.addEventListener('click', openProblemByRef);
openProblemRef.addEventListener('keydown', e => {
  if (e.key === 'Enter') openProblemByRef();
});
syncOpenProblemInputUI();
