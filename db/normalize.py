"""DB에서 읽은 문제 행(row)의 공통 필드를 정규화하는 헬퍼."""
import json

from constants import TIER_NAMES, normalize_platform


def resolve_tier_name(tier, tier_name) -> str:
    return tier_name or TIER_NAMES.get(tier, "Unrated")


def normalize_common_row(row: dict) -> dict:
    row["platform"] = normalize_platform(row.get("platform"))
    row["problem_ref"] = row.get("problem_ref") or str(row.get("problem_id", ""))
    if isinstance(row.get("tags"), str):
        row["tags"] = json.loads(row["tags"])
    row["tier_name"] = resolve_tier_name(row.get("tier", 0), row.get("tier_name"))
    return row
