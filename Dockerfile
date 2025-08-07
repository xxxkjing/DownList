FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements_web.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements_web.txt

# 复制应用代码
COPY web_main.py .
COPY static/ ./static/
COPY templates/ ./templates/

# 创建下载目录
RUN mkdir -p /app/downloads

# 暴露端口
EXPOSE 5000

# 启动应用
CMD ["python", "web_main.py"]
