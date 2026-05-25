FROM python:3.11-slim

RUN pip install uv

COPY runtime/ /app/runtime/

WORKDIR /app

RUN mkdir -p /app/runtime/output /logs/verifier
