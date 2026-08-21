#!/usr/bin/env bash
# JS 정적 검사 — 빌드 스텝이 없어 브라우저에서만 파싱되는 코드를 CI 가 대신 본다.
#
# 워크플로에 인라인으로 두지 않고 파일로 뺀 이유: `node --check static/js/*.js` 처럼
# 한 줄로 쓰면 조용히 틀린다(Node 는 스크립트를 하나만 받고 나머지 위치 인자는 argv 가 된다
# — 20개 중 1개만 검사됐다). 파일로 두면 로컬에서도 같은 검사를 돌려볼 수 있다.
set -uo pipefail

JS_DIR="${1:-static/js}"
status=0

if ! command -v node > /dev/null 2>&1; then
  echo "node 를 찾을 수 없습니다. CI 는 actions/setup-node 로 설치하고,"
  echo "로컬에서 돌리려면 Node 를 설치하세요(구문 검사에만 필요합니다)."
  exit 1
fi

echo "== 구문 검사 =="
# 파일마다 따로 돌린다. glob 을 한 번에 넘기면 첫 파일만 검사된다.
count=0
for f in "$JS_DIR"/*.js; do
  if ! node --check "$f"; then
    echo "  구문 오류: $f"
    status=1
  fi
  count=$((count + 1))
done
echo "  ${count}개 파일 검사 완료"
if [ "$count" -eq 0 ]; then
  echo "  검사할 파일이 없습니다 — 경로가 맞습니까? ($JS_DIR)"
  exit 1
fi

echo "== 최상위 렉시컬 선언 중복 검사 =="
# 스크립트가 전역 렉시컬 스코프를 공유하므로, 최상위 let/const/class 이름이 겹치면
# 전체 스크립트가 SyntaxError 로 죽는다(앱 전체 무음 실패의 단일 지점).
# var 와 function 의 재선언은 **합법**이므로 게이트에 넣지 않는다 — 넣으면 정상 코드에
# 거짓 빨강이 난다.
dupes=$(grep -hoE "^(const|let|class)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*" "$JS_DIR"/*.js \
        | awk '{print $NF}' | sort | uniq -d)
if [ -n "$dupes" ]; then
  echo "  최상위 렉시컬 선언이 중복됩니다 — 전역 스코프를 공유하므로 전체 스크립트가 죽습니다:"
  echo "$dupes" | sed 's/^/    /'
  status=1
else
  echo "  중복 없음"
fi

exit "$status"
