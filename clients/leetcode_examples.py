"""LeetCode 예제 케이스 추출 + Python 3 실행 하네스.

LeetCode 문제는 함수 시그니처 기반이라 stdin/stdout 실행기로 바로 채점할 수 없다. GraphQL
`question` 의 `exampleTestcases`(인자 한 줄씩, JSON)·`metaData`(함수명·인자 타입·반환 타입)와
본문 `Output:` 줄을 조합해 CF 와 같은 `samples` 로 만들고, 제출 코드 앞뒤에 붙여 stdin 인자를
`Solution().메서드(...)` 에 넘기고 결과를 JSON 한 줄로 찍는 하네스를 함께 준다.

Python 3 전용이다. 다루는 타입은 정수·실수·문자열·불·문자와 그 배열(중첩 포함), ListNode·
TreeNode 다. 그 밖(디자인 클래스 등)은 None 을 돌려 뷰어가 예제 실행 영역을 숨기게 한다.
"""
import json
import re

from clients.leetcode import _lc_html_to_text

_SCALAR_TYPES = {"integer", "long", "double", "string", "boolean", "character"}
_NODE_TYPES = {"ListNode", "TreeNode"}
_OUTPUT_RE = re.compile(r"^Output:\s*(.+?)\s*$", re.M)

# 제출 코드 앞. LeetCode 실행 환경이 미리 넣어 주는 typing 이름들과, 스니펫에 주석으로만 있는
# ListNode·TreeNode 정의다. 사용자가 직접 정의하면 그쪽이 이 정의를 덮는다.
PRELUDE = """from typing import *
import collections, itertools, functools, math, heapq, bisect
from collections import defaultdict, deque, Counter, OrderedDict
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right
"""

# 제출 코드 뒤. 이름은 전부 _lc_ 접두사다 — 사용자 코드의 식별자와 겹치지 않게.
_EPILOGUE_TEMPLATE = """
import sys as _lc_sys, json as _lc_json, collections as _lc_collections
_LC_NAME = {name!r}
_LC_PARAMS = {params!r}
_LC_RETURN = {ret!r}
_LC_OUTPUT_INDEX = {output_index!r}
def _lc_from_list(values):
    head = None
    for v in reversed(values):
        head = ListNode(v, head)
    return head
def _lc_to_list(node):
    out = []
    while node is not None:
        out.append(node.val)
        node = node.next
    return out
def _lc_from_tree(values):
    if not values or values[0] is None:
        return None
    root = TreeNode(values[0])
    queue = _lc_collections.deque([root])
    i = 1
    while queue and i < len(values):
        node = queue.popleft()
        if values[i] is not None:
            node.left = TreeNode(values[i])
            queue.append(node.left)
        i += 1
        if i < len(values) and values[i] is not None:
            node.right = TreeNode(values[i])
            queue.append(node.right)
        i += 1
    return root
def _lc_to_tree(root):
    out = []
    queue = _lc_collections.deque([root])
    while queue:
        node = queue.popleft()
        if node is None:
            out.append(None)
            continue
        out.append(node.val)
        queue.append(node.left)
        queue.append(node.right)
    while out and out[-1] is None:
        out.pop()
    return out
def _lc_convert(value, kind):
    if kind.endswith("[]"):
        return [_lc_convert(v, kind[:-2]) for v in value]
    if kind == "ListNode":
        return _lc_from_list(value)
    if kind == "TreeNode":
        return _lc_from_tree(value)
    return value
def _lc_serialize(value, kind):
    if kind.endswith("[]") and isinstance(value, list):
        return [_lc_serialize(v, kind[:-2]) for v in value]
    if kind == "ListNode":
        return _lc_to_list(value)
    if kind == "TreeNode":
        return _lc_to_tree(value)
    return value
def _lc_main():
    lines = _lc_sys.stdin.read().split("\\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) != len(_LC_PARAMS):
        raise SystemExit(f"입력은 인자당 한 줄(JSON)로 {{len(_LC_PARAMS)}}줄이어야 합니다. 받은 줄 수: {{len(lines)}}")
    args = [_lc_convert(_lc_json.loads(line), kind) for line, kind in zip(lines, _LC_PARAMS)]
    result = getattr(Solution(), _LC_NAME)(*args)
    kind = _LC_RETURN
    if _LC_OUTPUT_INDEX is not None:
        result, kind = args[_LC_OUTPUT_INDEX], _LC_PARAMS[_LC_OUTPUT_INDEX]
    print(_lc_json.dumps(_lc_serialize(result, kind), separators=(",", ":"), ensure_ascii=False))
_lc_main()
"""


def _type_supported(kind: str) -> bool:
    base = kind
    while base.endswith("[]"):
        base = base[:-2]
    return base in _SCALAR_TYPES or base in _NODE_TYPES


def _normalize_output(text: str) -> str | None:
    """본문의 기대 출력을 하네스 출력 형식(공백 없는 JSON)에 맞춘다.

    JSON 이 아니면 None — `2, nums = [2,2,_,_]` 같은 커스텀 채점 표기는 하네스의 JSON 출력과
    절대 일치하지 않아 정답도 항상 실패한다.
    """
    try:
        return json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
    except ValueError:
        return None


def _expected_outputs(content_html: str) -> list[str | None]:
    return [_normalize_output(m) for m in _OUTPUT_RE.findall(_lc_html_to_text(content_html))]


def build_lc_examples(meta_data: str, example_testcases: str, content_html: str) -> dict | None:
    """{"samples": [{input, output}], "harness": {prelude, epilogue}} 또는 None.

    None 인 경우: metaData 가 함수 시그니처가 아니거나(디자인 문제) 타입을 못 다루거나,
    exampleTestcases 줄 수가 인자 수의 배수가 아니거나 본문 Output 개수가 케이스 수와 다르거나,
    기대 출력이 JSON 이 아닐 때(커스텀 채점 문제).
    """
    try:
        meta = json.loads(meta_data or "")
    except ValueError:
        return None
    if not isinstance(meta, dict) or meta.get("classname") or not meta.get("name"):
        return None
    params = [p.get("type") or "" for p in (meta.get("params") or [])]
    ret = (meta.get("return") or {}).get("type") or ""
    if not params or not all(_type_supported(t) for t in params):
        return None
    if ret != "void" and not _type_supported(ret):
        return None

    lines = (example_testcases or "").split("\n")
    if len(lines) % len(params):
        return None
    cases = [lines[i:i + len(params)] for i in range(0, len(lines), len(params))]
    expected = _expected_outputs(content_html)
    if not cases or len(expected) != len(cases) or None in expected:
        return None

    output_index = None
    if ret == "void":
        # in-place 문제는 LeetCode 가 첫 인자(또는 output.paramindex 인자)를 출력으로 삼는다.
        output_index = int((meta.get("output") or {}).get("paramindex", 0))
        if not 0 <= output_index < len(params):
            return None
    epilogue = _EPILOGUE_TEMPLATE.format(name=meta["name"], params=params, ret=ret,
                                         output_index=output_index)
    return {
        "samples": [{"input": "\n".join(c), "output": o} for c, o in zip(cases, expected)],
        "harness": {"prelude": PRELUDE, "epilogue": epilogue},
    }
