FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（Edge TTS 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ backend/
COPY .env.example .env

EXPOSE 3010

CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "3010"]
