# telegram-sql-bot

텔레그램 명령으로 Cloud SQL 인스턴스 `boj-review-db` 를 온디맨드로 시작/정지하는 gen2 Cloud Function.

BOJ 코드리뷰의 24/7 GCP 비용은 상시 실행되는 Cloud SQL(`db-f1-micro`)에서 발생한다.
리뷰할 때만 DB를 켜고 끝나면 꺼서 비용을 절감한다.

## 명령

| 명령 | 동작 |
|---|---|
| `/start_sql` | DB 시작 (`activationPolicy=ALWAYS`). 1~2분 후 사용 가능 |
| `/stop_sql` | DB 정지 (`activationPolicy=NEVER`). 비용 절감 |
| `/status` | 현재 상태(state + activationPolicy) 조회 |

DB가 정지된 동안에는 Cloud Run 리뷰 앱의 DB 의존 기능이 실패한다.
워크플로: 평소 정지 → 리뷰 전 `/start_sql` → 리뷰 → `/stop_sql`.

## 보안

- 텔레그램이 보내는 `X-Telegram-Bot-Api-Secret-Token` 헤더를 `TELEGRAM_WEBHOOK_SECRET` 과 비교.
- 발신 `chat.id` 가 `TELEGRAM_ALLOWED_CHAT_ID` 와 일치하는지 확인.
- 둘 중 하나라도 불일치하면 아무 동작 없이 `200` 반환(재시도 방지).

## 설정 · 배포

### 1. 봇 생성 (텔레그램 앱)
BotFather 에게 `/newbot` → 봇 토큰 확보.

### 2. 본인 chat id 확인
봇에게 아무 메시지나 보낸 뒤:
```
curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
```
응답의 `message.chat.id` 가 `TELEGRAM_ALLOWED_CHAT_ID`.

### 3. webhook secret 생성
```
export TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 32)
```

### 4. 봇 토큰을 Secret Manager 에 저장
```
printf '%s' "<TOKEN>" | gcloud secrets create telegram-bot-token \
  --project boj-code-review-2024 --data-file=-
# 이미 있으면: gcloud secrets versions add telegram-bot-token --data-file=- <<< "<TOKEN>"
```

### 5. 배포
```
export TELEGRAM_ALLOWED_CHAT_ID=<본인 chat id>
./deploy.sh
```
스크립트가 마지막에 함수 URL 을 출력한다.

### 6. 런타임 서비스 계정에 Cloud SQL 권한 부여
함수 런타임 SA(기본 `707325519995-compute@developer.gserviceaccount.com`)에:
```
gcloud projects add-iam-policy-binding boj-code-review-2024 \
  --member="serviceAccount:707325519995-compute@developer.gserviceaccount.com" \
  --role="roles/cloudsql.admin"
```

### 7. 텔레그램 webhook 등록
```
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<함수URL>&secret_token=${TELEGRAM_WEBHOOK_SECRET}"
```

## 검증
1. 봇에게 `/status` → 상태 회신 확인.
2. `/stop_sql` → 회신 후
   `gcloud sql instances describe boj-review-db --format="value(state,settings.activationPolicy)"` 로 `NEVER` 확인.
3. `/start_sql` → 1~2분 후 `RUNNABLE`/`ALWAYS` 복귀, 리뷰 앱 정상 동작 확인.
