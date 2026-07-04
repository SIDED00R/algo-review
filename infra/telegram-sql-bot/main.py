"""텔레그램 웹훅 → Cloud SQL 인스턴스 온디맨드 시작/정지.

BOJ 코드리뷰의 24/7 비용 원인인 Cloud SQL 인스턴스를 필요할 때만 켜기 위한
gen2 Cloud Function. 텔레그램 봇 명령(/start_sql, /stop_sql, /status)을 받아
SQL Admin API로 settings.activationPolicy 를 ALWAYS/NEVER 로 전환한다.

보안: 텔레그램이 보내는 secret 토큰 헤더 + 발신 chat_id 화이트리스트로 이중 검증.
검증 실패 시 아무 동작 없이 200 을 반환해 텔레그램 재시도를 막는다.
"""

import logging
import os

import functions_framework
import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

PROJECT = os.environ["GCP_PROJECT"]
INSTANCE = os.environ["SQL_INSTANCE"]
ALLOWED_CHAT_ID = os.environ["TELEGRAM_ALLOWED_CHAT_ID"].strip()
WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
_HELP = (
    "🗄️ Cloud SQL 제어 봇\n"
    "/start_sql — DB 시작 (리뷰 전, 1~2분 소요)\n"
    "/stop_sql — DB 정지 (리뷰 후, 비용 절감)\n"
    "/status — 현재 상태 확인"
)


def _sql():
    return build("sqladmin", "v1", cache_discovery=False)


def _set_activation(policy: str) -> None:
    """activationPolicy 를 ALWAYS(시작)/NEVER(정지) 로 전환."""
    _sql().instances().patch(
        project=PROJECT,
        instance=INSTANCE,
        body={"settings": {"activationPolicy": policy}},
    ).execute()


def _status() -> str:
    # activationPolicy 가 유일하게 신뢰할 수 있는 켜짐/꺼짐 기준.
    # API 의 state 필드는 정지 상태에서도 RUNNABLE 로 남으므로 판단에 쓰지 않는다.
    inst = _sql().instances().get(project=PROJECT, instance=INSTANCE).execute()
    policy = inst.get("settings", {}).get("activationPolicy")
    if policy != "ALWAYS":
        return "정지됨 — /start_sql 로 시작하세요"
    if inst.get("state") == "RUNNABLE":
        return "사용 가능"
    return "시작 중 — 잠시 후 사용 가능"


def _reply(chat_id, text: str) -> None:
    try:
        requests.post(
            f"{_API_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except requests.RequestException:
        pass  # 응답 실패는 무시 — 명령 자체는 이미 처리됨


def _dispatch(command: str, chat_id) -> None:
    try:
        if command == "/start_sql":
            _set_activation("ALWAYS")
            _reply(chat_id, "✅ DB 시작 요청 완료. 1~2분 후 사용 가능합니다.")
        elif command == "/stop_sql":
            _set_activation("NEVER")
            _reply(chat_id, "🛑 DB 정지 요청 완료. 비용이 절감됩니다.")
        elif command == "/status":
            _reply(chat_id, f"📊 상태: {_status()}")
        else:
            _reply(chat_id, _HELP)
    except Exception as e:  # noqa: BLE001 — 모든 API 오류를 사용자에게 회신
        if isinstance(e, HttpError) and e.resp.status == 409:  # 이전 작업이 아직 진행 중
            _reply(chat_id, "⏳ 이전 작업이 진행 중입니다. 1~2분 후 다시 시도하세요.")
            return
        logging.exception("command %s failed", command)
        _reply(chat_id, f"⚠️ 오류: {type(e).__name__}: {e}")


@functions_framework.http
def handle(request):
    # 1) secret 토큰 헤더 검증
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return ("", 200)

    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message")
    if not message:
        return ("", 200)

    chat_id = message.get("chat", {}).get("id")
    # 2) chat_id 화이트리스트 검증
    if str(chat_id) != ALLOWED_CHAT_ID:
        return ("", 200)

    text = (message.get("text") or "").strip()
    # "/start_sql@MyBot" → "/start_sql"
    command = text.split()[0].split("@")[0] if text else ""
    _dispatch(command, chat_id)
    return ("", 200)
