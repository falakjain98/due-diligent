# Screener API image: small base, pinned dependencies, runs as a non-root user.
FROM python:3.13-slim

# Don't write .pyc files, print logs straight away, keep pip's download cache out of the image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) Dependencies first, read from pyproject.toml so the pins live in one place.
#    This layer is rebuilt only when pyproject.toml changes, not on every code edit.
COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

# 2) Then our own code (changes often, so it comes last). --no-deps: already installed above.
COPY README.md .
COPY src/ src/
COPY sample_data/ sample_data/
RUN pip install --no-deps .

# 3) Drop root. uid 1000 matches the default user on most EC2 images, so mounted folders stay readable.
RUN useradd --uid 1000 --create-home appuser
USER appuser

EXPOSE 8000

# Docker marks the container unhealthy if /health stops answering. slim has no curl, so use Python.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"

# 0.0.0.0 = listen on every network interface, so traffic from outside the container gets in.
CMD ["uvicorn", "due_diligent.api:app", "--host", "0.0.0.0", "--port", "8000"]