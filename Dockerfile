# Usamos uma imagem Python leve em vez da imagem pesada do Playwright
FROM python:3.11-slim

# Instalar dependências de sistema necessárias para o Playwright
RUN apt-get update && apt-get install -y \
    libevent-2.1-7 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Primeiro copiamos apenas o requirements para aproveitar o CACHE do Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalamos APENAS o navegador Chromium (economiza +1GB de download)
RUN playwright install chromium --with-deps

# Agora copiamos o restante do código
COPY . .

# Comando para rodar a API (ajuste o nome do arquivo se não for main.py)
CMD ["uvicorn", "main_otp:app", "--host", "0.0.0.0", "--port", "8080"]
