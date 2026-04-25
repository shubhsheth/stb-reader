FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY stb_reader/ stb_reader/
COPY server/ server/
RUN pip install ".[server]"
EXPOSE 8000
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
