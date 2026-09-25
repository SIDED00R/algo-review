"""clients/leetcode_examples — 예제 케이스 추출과 Python 하네스. 하네스는 실제 파이썬 자식 프로세스로 돌린다."""
import json
import subprocess
import sys

import pytest

from clients.leetcode_examples import build_lc_examples

_TWO_SUM_META = json.dumps({"name": "twoSum", "params": [{"name": "nums", "type": "integer[]"},
                                                         {"name": "target", "type": "integer"}],
                            "return": {"type": "integer[]"}})
_TWO_SUM_HTML = ("<p>Given <code>nums</code>.</p>"
                 "<pre>\n<strong>Input:</strong> nums = [2,7,11,15], target = 9\n"
                 "<strong>Output:</strong> [0,1]\n<strong>Explanation:</strong> because.\n</pre>"
                 "<pre>\n<strong>Input:</strong> nums = [3,3], target = 6\n<strong>Output:</strong> [0, 1]\n</pre>")
_TWO_SUM_CASES = "[2,7,11,15]\n9\n[3,3]\n6"

# 최근 문제의 본문 형식 — <pre> 대신 example-block div 와 <span class="example-io">.
_NEW_STYLE_HTML = ('<div class="example-block"><p><strong>Input:</strong> '
                   '<span class="example-io">s = "abc"</span></p>'
                   '<p><strong>Output:</strong> <span class="example-io">true</span></p></div>')


def _run(examples: dict, solution: str, stdin: str) -> subprocess.CompletedProcess:
    code = f"{examples['harness']['prelude']}\n{solution}\n{examples['harness']['epilogue']}"
    return subprocess.run([sys.executable, "-I", "-X", "utf8=1", "-c", code], input=stdin,
                          capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_samples_pair_argument_lines_with_normalized_outputs():
    ex = build_lc_examples(_TWO_SUM_META, _TWO_SUM_CASES, _TWO_SUM_HTML)
    assert ex["samples"] == [
        {"input": "[2,7,11,15]\n9", "output": "[0,1]"},
        {"input": "[3,3]\n6", "output": "[0,1]"},   # "[0, 1]" 도 하네스 출력 형식으로 정규화된다
    ]
    assert "class ListNode" in ex["harness"]["prelude"]
    assert "_LC_NAME = 'twoSum'" in ex["harness"]["epilogue"]


def test_new_style_example_block_is_parsed():
    meta = json.dumps({"name": "check", "params": [{"name": "s", "type": "string"}],
                       "return": {"type": "boolean"}})
    ex = build_lc_examples(meta, '"abc"', _NEW_STYLE_HTML)
    assert ex["samples"] == [{"input": '"abc"', "output": "true"}]


@pytest.mark.parametrize("meta, cases, html", [
    # 디자인 문제(클래스) — 함수 시그니처가 아니다
    (json.dumps({"classname": "LRUCache", "constructor": {}, "methods": []}), "x", _TWO_SUM_HTML),
    # 하네스가 못 다루는 타입
    (json.dumps({"name": "f", "params": [{"name": "g", "type": "Node"}], "return": {"type": "integer"}}),
     "[1]", "<pre>Output: 1</pre>"),
    # 인자 줄 수가 인자 수의 배수가 아니다
    (_TWO_SUM_META, "[2,7]\n9\n[3,3]", _TWO_SUM_HTML),
    # 본문 Output 개수가 케이스 수와 다르다
    (_TWO_SUM_META, _TWO_SUM_CASES, "<pre>Output: [0,1]</pre>"),
    # metaData 가 JSON 이 아니다(유료 문제는 빈 문자열)
    ("", "", ""),
    # 기대 출력이 JSON 이 아니다(27번 같은 커스텀 채점 표기) — 하네스의 JSON 출력과 절대 맞지 않는다
    (_TWO_SUM_META, "[3,2,2,3]\n3", "<pre>Output: 2, nums = [2,2,_,_]</pre>"),
])
def test_unsupported_or_inconsistent_problems_give_none(meta, cases, html):
    assert build_lc_examples(meta, cases, html) is None


def test_harness_runs_two_sum_and_prints_compact_json():
    ex = build_lc_examples(_TWO_SUM_META, _TWO_SUM_CASES, _TWO_SUM_HTML)
    solution = ("class Solution:\n"
                "    def twoSum(self, nums: List[int], target: int) -> List[int]:\n"
                "        seen = {}\n"
                "        for i, n in enumerate(nums):\n"
                "            if target - n in seen: return [seen[target - n], i]\n"
                "            seen[n] = i\n")
    for sample in ex["samples"]:
        proc = _run(ex, solution, sample["input"])
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == sample["output"]


def test_harness_converts_list_and_tree_nodes_both_ways():
    meta = json.dumps({"name": "f", "params": [{"name": "l", "type": "ListNode"},
                                               {"name": "root", "type": "TreeNode"}],
                       "return": {"type": "ListNode"}})
    html = "<pre>Output: [3,9,20,15,7,1,2]</pre>"
    ex = build_lc_examples(meta, "[1,2]\n[3,9,20,null,null,15,7]", html)
    # 연결 리스트 뒤에 트리의 레벨 순서 값을 이어 붙여 돌려준다 — 트리 복원과 리스트 직렬화를 함께 본다.
    solution = ("class Solution:\n"
                "    def f(self, l, root):\n"
                "        vals = []\n"
                "        q = deque([root])\n"
                "        while q:\n"
                "            n = q.popleft()\n"
                "            if n: vals.append(n.val); q.append(n.left); q.append(n.right)\n"
                "        cur = l\n"
                "        while cur.next: cur = cur.next\n"
                "        for v in vals[2:]: cur.next = ListNode(v); cur = cur.next\n"
                "        return l\n")
    proc = _run(ex, solution, ex["samples"][0]["input"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[1,2,20,15,7]"


def test_harness_returns_tree_in_level_order_without_trailing_nulls():
    meta = json.dumps({"name": "invertTree", "params": [{"name": "root", "type": "TreeNode"}],
                       "return": {"type": "TreeNode"}})
    ex = build_lc_examples(meta, "[4,2,7,1,null,null,9]", "<pre>Output: [4,7,2,9,null,null,1]</pre>")
    solution = ("class Solution:\n"
                "    def invertTree(self, root):\n"
                "        if root: root.left, root.right = self.invertTree(root.right), self.invertTree(root.left)\n"
                "        return root\n")
    proc = _run(ex, solution, ex["samples"][0]["input"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[4,7,2,9,null,null,1]"


def test_void_return_prints_the_in_place_argument():
    meta = json.dumps({"name": "rotate", "params": [{"name": "nums", "type": "integer[]"},
                                                    {"name": "k", "type": "integer"}],
                       "return": {"type": "void"}, "output": {"paramindex": 0}})
    ex = build_lc_examples(meta, "[1,2,3,4,5,6,7]\n3", "<pre>Output: [5,6,7,1,2,3,4]</pre>")
    solution = ("class Solution:\n"
                "    def rotate(self, nums, k):\n"
                "        k %= len(nums)\n"
                "        nums[:] = nums[-k:] + nums[:-k]\n")
    proc = _run(ex, solution, ex["samples"][0]["input"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[5,6,7,1,2,3,4]"


def test_wrong_argument_line_count_fails_with_a_readable_message():
    ex = build_lc_examples(_TWO_SUM_META, _TWO_SUM_CASES, _TWO_SUM_HTML)
    proc = _run(ex, "class Solution:\n    def twoSum(self, nums, target): return []\n", "[1,2]")
    assert proc.returncode != 0
    assert "2줄이어야" in proc.stderr and "받은 줄 수: 1" in proc.stderr
