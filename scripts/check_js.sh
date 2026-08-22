#!/usr/bin/env bash
# JS 정적 검사 — 빌드 스텝이 없어 브라우저에서만 파싱되는 코드를 CI 가 대신 본다.
#
# 워크플로에 인라인으로 두지 않고 파일로 뺀다: `node --check static/js/*.js` 처럼 한 줄로
# 쓰면 조용히 틀린다(Node 는 스크립트를 하나만 받고 나머지 위치 인자는 argv 가 된다).
# 파일로 두면 로컬에서도 같은 검사를 돌려볼 수 있다.
set -uo pipefail
# nullglob 없이는 매치가 없을 때 glob 이 리터럴로 남아 루프가 1회 돈다 —
# 경로가 틀렸는데 "1개 파일 검사 완료" 가 찍혀 검사 개수를 신뢰할 수 없다.
shopt -s nullglob

JS_DIR="${1:-static/js}"
# 로드 누락 검사가 볼 HTML — JS_DIR 을 바꿔 부르면 이것도 함께 바꿔야 한다.
HTML_FILE="${2:-static/index.html}"
CSS_DIR="${3:-static/css}"
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

  # 파일별 검사로는 **전역 스코프 충돌**을 볼 수 없다. 브라우저는 이 파일들을 하나의
  # 전역 렉시컬 환경에서 평가하므로, 전부 이어 붙여 한 번 더 파싱하면 실제 실행 조건과
  # 같아진다 — 아래 grep 검사가 놓치는 다중 선언자(`const a = 1, b = 2`)와 구조 분해
  # (`const {a, b} = x`)까지 사양대로 잡힌다.
  # 이어 붙여도 새로 생기는 오류는 없다 — function 끼리·var 끼리 재선언은 합법이다.
  # (엄밀히는 파일 경계가 ASI 경계이기도 해서, 앞 파일이 세미콜론 없이 끝나고 뒤 파일이
  #  `(`·`[`·백틱 등으로 시작하면 합본에서만 의미가 달라질 수 있다. 현재 20개 파일은
  #  전부 `;` 또는 `}` 로 끝나 해당 없다.)
  # 확장자가 `.js` 여야 한다 — Node 22 는 확장자로 모듈 타입을 판정하고, mktemp 의
  # 무확장자 파일에는 ERR_UNKNOWN_FILE_EXTENSION 을 던진다(게이트 자체가 실패한다).
  # package.json 이 없으므로 `.js` 는 CommonJS 로 파싱된다. 브라우저의 classic script 와
  # **완전히 같지는 않다** — CJS 는 모듈 래퍼 함수 안이라 최상위 `return` 과 전역
  # 프로퍼티 섀도잉(`const location = …`)을 통과시킨다. 이름 충돌 검사가 목적이므로
  # 그 차이는 감수한다.
  tmpdir=$(mktemp -d) || { echo "  임시 디렉터리를 만들 수 없습니다"; exit 1; }
  combined="$tmpdir/_all.js"
  # 파일마다 개행을 덧붙인다 — 마지막 줄이 주석이면 다음 파일 첫 줄이 삼켜진다.
  for f in "${files[@]}"; do cat "$f"; echo; done > "$combined"
  if ! node --check "$combined" 2> "$combined.err"; then
    echo "  전역 스코프에서 충돌합니다 (파일별로는 통과):"
    sed 's/^/    /' "$combined.err"
    # 오류 줄번호를 원래 파일로 되돌려 준다.
    bad_line=$(grep -oE ":[0-9]+$" <<< "$(head -1 "$combined.err")" | tr -d ':')
    mapped=""
    if [ -n "$bad_line" ]; then
      offset=0
      for f in "${files[@]}"; do
        n=$(( $(wc -l < "$f") + 1 ))
        if [ "$bad_line" -le $(( offset + n )) ]; then
          echo "    → $f 부근 (합본 ${bad_line}행)"
          mapped=1
          break
        fi
        offset=$(( offset + n ))
      done
    fi
    # 매핑이 조용히 빠지면 "어느 파일인지 모른 채 exit 1" 이 된다 — 실패했다고 말한다.
    [ -n "$mapped" ] || echo "    → 원본 파일 매핑 실패 (합본 ${bad_line:-?}행, node 출력 형식 확인)"
    status=1
  else
    echo "  전역 스코프 합본 파싱도 통과"
  fi
  rm -rf "$tmpdir"
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
# 렉시컬끼리만 보면 교차 충돌(렉시컬 × function/var 조합)을 전부 놓친다.
# `var` 도 교차 충돌을 만들므로 함께 본다.
#
# 이 grep 검사는 위 합본 파싱보다 약하다(첫 선언자만 본다). 남겨 두는 이유는 두 가지다 —
# node 가 없어도 돌고, 충돌한 **이름을 짚어 준다**.
lexical=$(grep -hoE "^(const|let|class)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*" "${files[@]}"           | awk '{print $NF}' | sort)
vars=$(grep -hoE "^((async[[:space:]]+)?function|var)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*" "${files[@]}"         | awk '{print $NF}' | sort -u)

lex_dupes=$(echo "$lexical" | uniq -d)
cross=$(comm -12 <(echo "$lexical" | uniq) <(echo "$vars"))

if [ -n "$lex_dupes" ]; then
  echo "  렉시컬 선언(let/const/class)이 중복됩니다 — 전체 스크립트가 SyntaxError 로 죽습니다:"
  echo "$lex_dupes" | sed 's/^/    /'
  status=1
fi
if [ -n "$cross" ]; then
  echo "  같은 이름이 렉시컬 선언과 function/var 선언 양쪽에 있습니다 — 이것도 SyntaxError 입니다:"
  echo "$cross" | sed 's/^/    /'
  status=1
fi
if [ -z "$lex_dupes" ] && [ -z "$cross" ]; then
  echo "  충돌 없음 (렉시컬 $(echo "$lexical" | uniq | grep -c .) 개 · function/var $(echo "$vars" | grep -c .) 개)"
fi

echo "== $HTML_FILE 로드 누락 검사 =="
# 자산이 조용히 고아가 되는 경로를 막는다 — 구문 검사는 통과하지만 페이지에 실리지 않는다.
# CSS 도 함께 본다: 로드 순서가 곧 캐스케이드 순서라 하나가 빠지면 화면이 통째로 바뀐다.
# nullglob 때문에 경로가 틀리면 목록이 통째로 사라져 "전부 참조됨" 이 찍힌다 — 먼저 센다.
css_files=("$CSS_DIR"/*.css)
if [ ${#css_files[@]} -eq 0 ]; then
  echo "  검사할 CSS 가 없습니다 — 경로가 맞습니까? ($CSS_DIR)"
  exit 1
fi
missing=""
for f in "${files[@]}" "${css_files[@]}"; do
  name=$(basename "$f")
  dir=$(basename "$(dirname "$f")")
  if ! grep -qF "$dir/$name?v=" "$HTML_FILE"; then
    missing="$missing$dir/$name
"
  fi
done
if [ -n "$missing" ]; then
  echo "  $HTML_FILE 이 참조하지 않는 자산이 있습니다:"
  printf "%b" "$missing" | sed 's/^/    /'
  status=1
else
  echo "  전부 참조됨"
fi

exit "$status"
