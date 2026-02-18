# Usar a imagem oficial do Playwright que já tem todas as libs e navegadores
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Definir diretório de trabalho
WORKDIR /app

# Copiar os arquivos do projeto
COPY requirements.txt .
COPY . .

# Instalar dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Variáveis de ambiente para o Playwright rodar no Docker
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Comando para rodar a aplicação
CMD ["uvicorn", "main_otp:app", "--host", "0.0.0.0", "--port", "8080"]
