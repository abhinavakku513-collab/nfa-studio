# The NFA Studio API. The host passes the port to listen on in $PORT.
FROM python:3.14-slim

# Graphviz lays out the diagrams (spec §10.2); it needs a font to measure label widths.
RUN apt-get update \
    && apt-get install -y --no-install-recommends graphviz fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY nfa_studio ./nfa_studio

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
# uvicorn would otherwise take the client address from X-Forwarded-For, which a client
# can forge; the rate limiter reads NFA_CLIENT_IP_HEADER instead (api/deps.py).
CMD ["sh", "-c", "exec uvicorn nfa_studio.api.app:app --host 0.0.0.0 --port \"$PORT\" --no-proxy-headers"]
