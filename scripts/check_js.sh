#!/usr/bin/env bash
# JS 정적 검사 — 빌드 스텝이 없어 브라우저에서만 파싱되는 코드를 CI 가 대신 본다.
#
# 워크플로에 인라인으로 두지 않고 파일로 뺀 이유: `node --check static/js/*.js` 처럼
# 한 줄로 쓰면 조용히 틀린다(Node 는 스크립트를 하나만 받고 나머지 위치 인자는 argv 가 된다
# — 20개 중 1개만 검사됐다). 파일로 두면 로컬에서도 같은 검사를 돌려볼 수 있다.
set -uo pipefail
# nullglob 없이는 매치가 없을 때 glob 이 리터럴로 남아 루프가 1회 돈다 —
# 경로가 틀렸는데 "1개 파일 검사 완료" 가 찍혀 검사 개수를 신뢰할 수 없다.
shopt -s nullglob

JS_DIR="${1:-static/js}"
status=0

# 파일 목록을 먼저 확정한다 — 아래 세 검사가 모두 이 목록에 의존한다.
files=("$JS_DIR"/*.js)
if [ ${#files[@]} -eq 0 ]; then
  echo "검사할 파일이 없습니다 — 경로가 맞습니까? ($JS_DIR)"
  exit 1
fi

echo "== 구문 검사 =="
if command -v node > /dev/null 2>&1; then
  # 파일마다 따로 돌린다. glob 을 한 번에 넘기면 Node 가 첫 파일만 검사한다
  # (스크립트는 하나만 받고 나머지 위치 인자는 argv 가 된다).
  for f in "${files[@]}"; do
    if ! node --check "$f"; then
      echo "  구문 오류: $f"
      status=1
    fi
  done
  echo "  ${#files[@]}개 파일 검사 완료"
else
  # 아래 두 검사는 node 없이도 유효하므로 여기서 중단하지 않는다.
  # CI 는 actions/setup-node 로 node 를 설치하므로 이 분기를 타지 않는다.
  echo "  node 가 없어 건너뜁니다(로컬). CI 에서는 반드시 실행됩니다."
  if [ "${CI:-}" = "true" ]; then
    echo "  CI 인데 node 가 없습니다 — setup-node 스텝을 확인하세요."
    exit 1
  fi
fi

echo "== 최상위 선언 충돌 검사 =="
# 스크립트가 전역 렉시컬 스코프를 공유하므로, 이름이 겹치면 전체 스크립트가 SyntaxError 로
# 죽는다(앱 전체 무음 실패의 단일 지점).
#
# ECMA-262 GlobalDeclarationInstantiation 기준으로 무엇이 SyntaxError 인가:
#   let/const/class 끼리 중복            → SyntaxError
#   let/const/class  ×  function/var     → SyntaxError  (교차 충돌)
#   function 끼리 / var 끼리             → 합법 (재할당일 뿐)
# 예전에는 렉시컬끼리만 봐서 **교차 충돌을 전부 놓쳤다** — 전역 함수 73개 × 렉시컬 36개
# 조합이 게이트 밖이었다.
lexical=$(grep -hoE "^(const|let|class)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*" "${files[@]}"           | awk '{print $NF}' | sort)
funcs=$(grep -hoE "^(async[[:space:]]+)?function[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*" "${files[@]}"         | awk '{print $NF}' | sort -u)

lex_dupes=$(echo "$lexical" | uniq -d)
cross=$(comm -12 <(echo "$lexical" | uniq) <(echo "$funcs"))

if [ -n "$lex_dupes" ]; then
  echo "  렉시컬 선언(let/const/class)이 중복됩니다 — 전체 스크립트가 SyntaxError 로 죽습니다:"
  echo "$lex_dupes" | sed 's/^/    /'
  status=1
fi
if [ -n "$cross" ]; then
  echo "  같은 이름이 렉시컬 선언과 function 선언 양쪽에 있습니다 — 이것도 SyntaxError 입니다:"
  echo "$cross" | sed 's/^/    /'
  status=1
fi
if [ -z "$lex_dupes" ] && [ -z "$cross" ]; then
  echo "  충돌 없음 (렉시컬 $(echo "$lexical" | uniq | grep -c .) 개 · function $(echo "$funcs" | grep -c .) 개)"
fi

echo "== index.html 로드 누락 검사 =="
# JS 파일이 조용히 고아가 되는 경로를 막는다 — 구문 검사는 통과하지만 페이지에 실리지 않는다.
missing=""
for f in "${files[@]}"; do
  name=$(basename "$f")
  if ! grep -q "js/$name?v=" static/index.html; then
    missing="$missing$name
"
  fi
done
if [ -n "$missing" ]; then
  echo "  index.html 이 참조하지 않는 JS 파일이 있습니다:"
  printf "%b" "$missing" | sed 's/^/    /'
  status=1
else
  echo "  전부 참조됨"
fi

exit "$status"
