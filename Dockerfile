# Imagem única do app (dev e produção). Python igual ao do host (3.14).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    MEDIA_ROOT=/data/media

# Usuário sem privilégios com o mesmo UID/GID do host (1000), para que os
# arquivos criados no bind mount do desenvolvimento fiquem com o seu dono.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" app \
    && useradd --uid "${UID}" --gid "${GID}" --create-home --shell /bin/bash app

WORKDIR /app

# requirements.txt em produção; requirements-dev.txt no compose local.
ARG REQUIREMENTS=requirements.txt
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r "${REQUIREMENTS}"

# O código fica com dono root: o processo do app (usuário app) lê, mas não altera.
# Só os estáticos e a pasta de fotos são do usuário app. No desenvolvimento o
# bind mount (.:/app) troca /app pelos arquivos do host, com o seu usuário.
COPY . .

# Estáticos com hash e compressão (whitenoise). A chave aqui só vale para o build.
RUN DEBUG=false SECRET_KEY=build-only-nao-usada-em-runtime \
    python manage.py collectstatic --noinput --verbosity 0 \
    && mkdir -p /data/media \
    && chown -R app:app /app/staticfiles /data

USER app

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["/app/docker/start.sh"]
