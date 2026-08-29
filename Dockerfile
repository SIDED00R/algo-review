FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# non-root 로 돌려 /app 코드 변조와 root 전용 자원 접근을 막는다.
# /app 은 root 소유로 남겨(chown 하지 않는다) appuser 에게 읽기·실행만 준다 — 쓰기가 필요한
# 데모 SQLite 는 DB_PATH 로 /tmp 를 쓴다(배포 워크플로).
#
# ⚠ non-root 는 `/proc/1/environ` 을 막지 못한다. USER 가 CMD 앞에 있으므로 uvicorn(PID 1)도
# appuser 로 뜨고, 같은 uid 면 /proc/<pid>/environ 을 읽을 수 있다. 그래서 임의 코드 실행은
# 이 이미지 안에서 하지 않고 `EXECUTOR_URL` 의 실행 전용 서비스로 위임한다 —
# 자세한 이유는 routes/execute.py 주석 참조.
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8080

# PORT 는 Cloud Run 이 주입한다. 하드코딩하면 서비스가 다른 포트로 설정될 때 컨테이너가
# 트래픽을 받지 못한다. 셸 폼이라 ${PORT} 가 확장되고, 미설정 로컬에서는 8080 이다.
CMD exec python -m uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}
