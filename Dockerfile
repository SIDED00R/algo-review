FROM python:3.13-slim

RUN apt-get update && apt-get install -y g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# /api/execute 가 인증 없는 공개 경로에서 임의 코드를 서브프로세스로 돌린다. root 로 두면 그 코드가
# /proc/1/environ 으로 앱 환경변수를 읽거나 /app 의 코드를 변조할 수 있다.
# /app 은 root 소유로 남겨(chown 하지 않는다) appuser 에게 읽기·실행만 준다 — 쓰기가 필요한
# 데모 SQLite 는 DB_PATH 로 /tmp 를 쓴다(배포 워크플로).
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
