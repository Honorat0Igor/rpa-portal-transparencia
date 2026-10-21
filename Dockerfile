# Imagem oficial do Playwright: Chromium + dependências de sistema já instalados
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Usuário não-root (o Chromium da imagem já roda bem como pwuser)
RUN mkdir -p /app/output && chown -R pwuser:pwuser /app
USER pwuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
