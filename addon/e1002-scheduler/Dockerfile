ARG BUILD_FROM
FROM $BUILD_FROM

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip chromium fonts-dejavu fonts-liberation fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

COPY app /app
WORKDIR /app
ENV TZ=Asia/Singapore
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8098", "--proxy-headers"]
