#!/usr/bin/env bash
# JS 정적 검사 — 구문, 최상위 선언 충돌, index.html 로드 누락.
set -uo pipefail
# nullglob: 매치가 없으면 glob 이 리터럴로 남아 루프가 1회 돈다.
shopt -s nullglob

JS_DIR="${1:-static/js}"
HTML_FILE="${2:-static/index.html}"
CSS_DIR="${3:-static/css}"
status=0

files=("$JS_DIR"/*.js)
if [ ${#files[@]} -eq 0 ]; then
  echo "검사할 파일이 없습니다 — 경로가 맞습니까? ($JS_DIR)"
  exit 1
fi

echo "== 구문 검사 =="
if command -v node > /dev/null 2>&1; then
  # Node 는 스크립트를 하나만 받는다 — glob 을 넘기면 첫 파일만 검사한다.
  for f in "${files[@]}"; do
    if ! node --check "$f"; then
      echo "  구문 오류: $f"
      status=1
    fi
  done
  echo "  ${#files[@]}개 파일 검사 완료"

  # 브라우저는 이 파일들을 하나의 전역 렉시컬 환경에서 평가한다 — 합본을 파싱해야
  # 전역 스코프 충돌이 보인다. 확장자는 `.js` 여야 한다(Node 22 는 확장자로 모듈 타입을
  # 판정한다). package.json 이 없어 CommonJS 로 파싱된다.
  tmpdir=$(mktemp -d) || { echo "  임시 디렉터리를 만들 수 없습니다"; exit 1; }
  combined="$tmpdir/_all.js"
  # 개행을 덧붙인다 — 마지막 줄이 주석이면 다음 파일 첫 줄이 삼켜진다.
  for f in "${files[@]}"; do cat "$f"; echo; done > "$combined"
  if ! node --check "$combined" 2> "$combined.err"; then
    echo "  전역 스코프에서 충돌합니다 (파일별로는 통과):"
    sed 's/^/    /' "$combined.err"
    # 합본 줄번호를 원래 파일로 되돌린다.
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
    # 매핑 실패를 말한다 — 조용히 빠지면 어느 파일인지 모른 채 exit 1 이 된다.
    [ -n "$mapped" ] || echo "    → 원본 파일 매핑 실패 (합본 ${bad_line:-?}행, node 출력 형식 확인)"
    status=1
  else
    echo "  전역 스코프 합본 파싱도 통과"
  fi
  rm -rf "$tmpdir"
else
  # 아래 두 검사는 node 없이도 돈다.
  echo "  node 가 없어 건너뜁니다(로컬). CI 에서는 반드시 실행됩니다."
  if [ "${CI:-}" = "true" ]; then
    echo "  CI 인데 node 가 없습니다 — setup-node 스텝을 확인하세요."
    exit 1
  fi
fi

echo "== 최상위 선언 충돌 검사 =="
# ECMA-262 GlobalDeclarationInstantiation 기준 SyntaxError 조합:
#   let/const/class 끼리 중복        → SyntaxError
#   let/const/class × function/var   → SyntaxError
#   function 끼리 / var 끼리         → 합법
# 각 이름의 첫 선언자만 본다. node 없이도 동작한다.
lexical=$(grep -hoE "^(const|let|class)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*" "${files[@]}" \
  | awk '{print $NF}' | sort)
vars=$(grep -hoE "^((async[[:space:]]+)?function|var)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*" "${files[@]}" \
  | awk '{print $NF}' | sort -u)

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
# JS·CSS 가 index.html 에 `?v=` 와 함께 참조되는지 본다.
# 목록이 비면 검사가 성립하지 않는다 — 개수를 먼저 확인한다.
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
