import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from routes.models import PushReviewRequest
from routes.helpers import build_readme
from demo_mode import IS_DEMO

router = APIRouter()


@router.post("/api/push-review")
def push_review_to_github(req: PushReviewRequest):
    if IS_DEMO:
        return {"pushed": True, "repo": "demo_user/algorithm-solutions",
                "path": f"demo/{req.problem_ref}"}
    gh_settings = db.get_github_settings()
    if not gh_settings:
        raise HTTPException(status_code=400, detail="GitHub 연결이 필요합니다. 헤더의 '🐙 GitHub 연결' 버튼을 눌러주세요.")
    github_repo = gh_settings.get("target_repo", "")
    github_token = gh_settings.get("access_token", "")
    if not github_repo or not github_token:
        raise HTTPException(status_code=400, detail="GitHub 저장소를 선택해주세요.")

    ext = api_client._get_file_extension(req.language)
    url = req.url or api_client.get_problem_url(req.platform, req.problem_ref)

    if req.platform == "boj":
        tier_cat = req.tier_name.split()[0] if req.tier_name else "Unrated"
        folder = f"백준/{tier_cat}/{req.problem_ref}번. {req.title}"
        msg = f"[BOJ] {req.problem_ref}번. {req.title}"
        if not req.description:
            sections = api_client.get_boj_problem_sections(int(req.problem_ref))
            description = sections.get("description", "")
            input_desc  = sections.get("input", "")
            output_desc = sections.get("output", "")
        else:
            description, input_desc, output_desc = req.description, req.input_desc, req.output_desc
    else:
        folder = f"Codeforces/{req.problem_ref}. {req.title}"
        msg = f"[Codeforces] {req.problem_ref}. {req.title}"
        if not req.description:
            sections = api_client.get_cf_problem_sections(req.problem_ref)
            description = sections.get("description", "")
            input_desc  = sections.get("input", "")
            output_desc = sections.get("output", "")
        else:
            description, input_desc, output_desc = req.description, req.input_desc, req.output_desc

    readme = build_readme(req.problem_ref, req.title,
                          req.tier_name, req.tags, req.language, url,
                          description, input_desc, output_desc)
    ok = api_client.push_files_to_github(github_repo, github_token, [
        {"path": f"{folder}/README.md", "content": readme},
        {"path": f"{folder}/{req.problem_ref}{ext}", "content": req.code},
    ], msg)
    if not ok:
        raise HTTPException(status_code=500, detail="GitHub push에 실패했습니다.")
    return {"pushed": True, "repo": github_repo, "path": folder}
