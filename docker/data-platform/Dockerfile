FROM --platform=linux/amd64 python:3.11.17-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89
ARG LOCK_SHA256
ARG DOCKERFILE_SHA256
LABEL org.commodity.lock-sha256="${LOCK_SHA256}"
LABEL org.commodity.dockerfile-sha256="${DOCKERFILE_SHA256}"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
RUN mkdir -p /workspace/scripts/data /workspace/src /workspace/config /outputs /worktmp /input
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --no-deps -r /tmp/requirements.txt
RUN python -c "import duckdb, numpy, polars, pyarrow; assert duckdb.__version__ == '1.5.6'; assert numpy.__version__ == '2.4.6'; assert polars.__version__ == '1.44.2'; assert pyarrow.__version__ == '25.0.1'"
USER 65532:65532
CMD ["python", "--version"]
