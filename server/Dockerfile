FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY margen ./margen
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home margen && mkdir /data && chown margen:margen /data
USER margen
ENV MARGEN_DATA=/data
EXPOSE 8765
CMD ["uvicorn", "margen.app:app", "--host", "0.0.0.0", "--port", "8765"]
