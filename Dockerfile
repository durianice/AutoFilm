FROM python:3.12.4-alpine

ENV TZ=Asia/Shanghai

RUN apk update \
    && apk upgrade \
    && apk add bash \
    && rm -rf \
        /tep \
        /var/lib/apt/lists \
        /var/tmp

COPY requirements.txt requirements.txt

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && rm -rf requirements.txt

COPY app /app

VOLUME ["/config", "/logs", "/media"]
ENTRYPOINT ["python","/app/main.py"]
