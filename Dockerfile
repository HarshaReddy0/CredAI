FROM python:3.11-slim

# Hugging Face Spaces runs containers as uid 1000
RUN useradd -m -u 1000 user
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --chown=user requirements.txt .
USER user
ENV PATH="/home/user/.local/bin:$PATH" PYTHONUNBUFFERED=1 DATA_DIR=/app/data ENABLE_DEEPFACE=false
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . /app
RUN mkdir -p /app/data

ENV PORT=7860
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",7860)}/api/health')"
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
