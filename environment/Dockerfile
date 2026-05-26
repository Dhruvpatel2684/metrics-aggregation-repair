FROM python:3.11-slim

RUN pip install uv

COPY runtime/ /app/runtime/
COPY ../tests/ /tests/
COPY ../solution/ /solution/

WORKDIR /app

CMD ["python3", "/app/runtime/run_resolver.py"]
