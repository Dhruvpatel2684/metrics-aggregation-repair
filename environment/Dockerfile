FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TZ=UTC

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-minimal \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install pytest

RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime

WORKDIR /app

COPY runtime/ ./runtime/
