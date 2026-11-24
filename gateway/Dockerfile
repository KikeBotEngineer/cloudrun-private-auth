# Contexto de build = raíz del repo (reutiliza client/identity_token.py):
#   docker build -f gateway/Dockerfile .
# Tag legible + digest fijo (build reproducible); Dependabot propone el digest nuevo.
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY client/identity_token.py .
COPY gateway/app ./app

USER nobody
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
