# Contexto de build = raíz del repo (reutiliza client/identity_token.py):
#   docker build -f gateway/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY client/identity_token.py .
COPY gateway/app ./app

USER nobody
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
