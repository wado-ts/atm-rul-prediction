FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
	&& useradd --create-home --uid 10001 appuser

COPY . .
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 9002

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
	CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9002/healthz')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9002"]
