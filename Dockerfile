# syntax=docker/dockerfile:1
# Base images are pinned by digest: a tag can be moved onto other code, and
# this image holds a mailbox credential at runtime. Dependabot bumps them.
FROM ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 AS uv

FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first, so a source change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE NOTICE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=8080
USER 10001
EXPOSE 8080
# The same image runs the egress-check job with `email-assistance-agent-egress-check`.
CMD ["email-assistance-agent"]
