# ─────────────────────────────────────────────────────────────────────────────
# AgentLumy — Image de production (Google Cloud Run)
#
# Deux étages : les dépendances sont compilées dans le premier, seul le résultat
# passe dans l'image finale. Les outils de build ne partent donc pas en
# production — image plus légère, démarrage à froid plus rapide, et moins de
# surface exposée.
#
# Build local :  docker build -t agentlumy-api .
# Test local  :  docker run --rm -p 8080:8080 --env-file .env agentlumy-api
# ─────────────────────────────────────────────────────────────────────────────

# ── Étage 1 : dépendances ────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# gcc est nécessaire à la compilation de certaines roues, pas à l'exécution :
# il reste donc dans cet étage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

# Copié seul et en premier : tant que ce fichier ne change pas, Docker réutilise
# le cache de cette couche au lieu de tout réinstaller à chaque build.
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt


# ── Étage 2 : image finale ───────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    APP_ENV=production

# L'application ne tourne pas en root : si le processus est compromis, il n'a
# aucun droit sur le système de fichiers de l'image.
RUN useradd --create-home --uid 1000 agentlumy

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=agentlumy:agentlumy app/ ./app/

USER agentlumy

EXPOSE 8080

# Cloud Run impose le port par la variable PORT et peut le changer : on la lit
# au démarrage plutôt que de coder 8080 en dur. La forme shell est nécessaire
# pour que $PORT soit substitué.
# Un seul worker par conteneur : Cloud Run monte en charge en ajoutant des
# instances, pas des processus.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
