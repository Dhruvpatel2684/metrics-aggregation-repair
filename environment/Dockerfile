FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-minimal \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install pytest

# Install uv as global system-wide tooling
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    mv /root/.local/bin/uvx /usr/local/bin/uvx 2>/dev/null || true

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime

WORKDIR /app

COPY runtime/ ./runtime/
