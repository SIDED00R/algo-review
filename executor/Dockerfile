FROM python:3.13-slim

# C++ 제출을 컴파일한다.
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/executor/requirements.txt
RUN pip install --no-cache-dir -r /app/executor/requirements.txt

# 패키지로 담는다 — WORKDIR 이 sys.path[0] 이라 `executor.main` 으로 import 된다.
COPY . /app/executor/

# 제출 코드는 이 프로세스와 같은 uid 로 돌아 `/proc/1/environ` 을 읽을 수 있다. 이 이미지에
# 시크릿·DB 접속·앱 코드를 넣지 않고, 런타임 서비스 계정에 권한을 주지 않는 이유다.
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 1000 runner
USER runner

EXPOSE 8080

CMD exec python -m uvicorn executor.main:app --host 0.0.0.0 --port ${PORT:-8080}
