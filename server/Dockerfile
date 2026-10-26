FROM python:3.13-slim
WORKDIR /app
# Revista 90's covers and openers are painted in the service: they need a font with accents.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-liberation && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml requirements.lock ./
COPY margen ./margen
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home margen && mkdir /data && chown margen:margen /data
USER margen
ENV MARGEN_DATA=/data
EXPOSE 8765
CMD ["uvicorn", "margen.app:app", "--host", "0.0.0.0", "--port", "8765"]
