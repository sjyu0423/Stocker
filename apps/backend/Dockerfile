FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps/backend ./apps/backend
RUN pip install --no-cache-dir .
CMD ["uvicorn", "marketmind.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

