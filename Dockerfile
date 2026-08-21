FROM python:3.13-slim

RUN apt-get update && apt-get install -y g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# non-root 로 돌려 /app 코드 변조와 root 전용 자원 접근을 막는다.
# /app 은 root 소유로 남겨(chown 하지 않는다) appuser 에게 읽기·실행만 준다 — 쓰기가 필요한
# 데모 SQLite 는 DB_PATH 로 /tmp 를 쓴다(배포 워크플로).
#
# ⚠ non-root 는 `/proc/1/environ` 을 막지 못한다. USER 가 CMD 앞에 있으므로 uvicorn(PID 1)도
# appuser 로 뜨고, 같은 uid 면 /proc/<pid>/environ 을 읽을 수 있다. 그래서 임의 코드 실행
# (/api/execute)은 여기서 막는 것이 아니라 `EXECUTE_ENABLED` 로 기본 비활성이다 —
# 자세한 이유는 routes/execute.py 주석 참조.
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
