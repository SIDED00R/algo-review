#!/usr/bin/env bash
# telegram-sql-bot 배포 스크립트.
# 사전 준비(README 참고): BotFather 봇 토큰, 본인 chat id, webhook secret.
# 사용법:
#   TELEGRAM_ALLOWED_CHAT_ID=123456789 TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 32) \
#     ./deploy.sh
# 봇 토큰은 Secret Manager 시크릿 telegram-bot-token 에 미리 저장해 둔다(README 4단계).
set -euo pipefail

PROJECT=boj-code-review-2024
REGION=asia-northeast3
INSTANCE=boj-review-db

: "${TELEGRAM_ALLOWED_CHAT_ID:?TELEGRAM_ALLOWED_CHAT_ID 를 설정하세요}"
: "${TELEGRAM_WEBHOOK_SECRET:?TELEGRAM_WEBHOOK_SECRET 를 설정하세요}"

cd "$(dirname "$0")"

gcloud functions deploy telegram-sql-bot \
  --gen2 --runtime python311 \
  --region "$REGION" --project "$PROJECT" \
  --source . --entry-point handle \
  --trigger-http --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=${PROJECT},SQL_INSTANCE=${INSTANCE},TELEGRAM_ALLOWED_CHAT_ID=${TELEGRAM_ALLOWED_CHAT_ID},TELEGRAM_WEBHOOK_SECRET=${TELEGRAM_WEBHOOK_SECRET}" \
  --set-secrets "TELEGRAM_BOT_TOKEN=telegram-bot-token:latest"

echo "배포 완료. 함수 URL 확인:"
gcloud functions describe telegram-sql-bot --gen2 --region "$REGION" --project "$PROJECT" \
  --format="value(serviceConfig.uri)"
