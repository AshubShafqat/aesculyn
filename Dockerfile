FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AESCULYN_HOST=0.0.0.0 AESCULYN_DATA=/data
WORKDIR /app
COPY requirements-research-lock.txt ./
RUN pip install --no-cache-dir -r requirements-research-lock.txt && useradd --uid 10001 --create-home app && mkdir /data && chown app:app /data
COPY app.py engine.py ./
COPY application/ ./application/
COPY research/ ./research/
COPY ids/ ./ids/
COPY RESEARCH_RESULTS.md APPLICATION.md ARCHITECTURE_AUDIT.md APPLICATION_VERIFICATION.md ./
COPY public/research.json ./public/research.json
USER app
EXPOSE 8780
CMD ["python", "app.py"]
