# Avishkar OS + Layla production runtime image -- Mission Layla
# Directive D, Part XVII (Production Deployment). See CONTRACT.md SS60
# and layla/OPERATIONS.md.
#
# Mirrors the exact PYTHONPATH composition every test run and example
# script in this repository already uses (layla/README.md's Testing
# Guide) rather than inventing a separate packaging/dependency scheme.
# This is a BASE runtime image: layla/deploy/run_production.py is a
# real, generic reference entrypoint (one "general-agent" domain) --
# an application-specific deployment builds its own agent roster on
# top of the same real ExecutiveRuntime/Orchestrator/ChiefDomainAgent
# components, FROM this image.
#
# Build (from the repository root):
#   docker build -f layla/Dockerfile -t avishkar-layla:local .
# Run:
#   docker run --rm -p 8080:8080 \
#     -e ANTHROPIC_API_KEY=sk-ant-... \
#     -v layla-data:/data/layla \
#     avishkar-layla:local

FROM python:3.11-slim AS runtime

WORKDIR /app

COPY core/python                          core/python
COPY router/python                        router/python
COPY factories/agent-factory/python       factories/agent-factory/python
COPY factories/knowledge-factory/python   factories/knowledge-factory/python
COPY factories/mcp-factory/python         factories/mcp-factory/python
COPY factories/memory-factory/python      factories/memory-factory/python
COPY factories/security-factory/python    factories/security-factory/python
COPY factories/evaluation-factory/python  factories/evaluation-factory/python
COPY factories/prompt-factory/python      factories/prompt-factory/python
COPY factories/workflow-factory/python    factories/workflow-factory/python
COPY layla/python                         layla/python
COPY layla/deploy                         layla/deploy

ENV PYTHONPATH="/app/core/python:/app/router/python:/app/factories/agent-factory/python:/app/factories/knowledge-factory/python:/app/factories/mcp-factory/python:/app/factories/memory-factory/python:/app/factories/security-factory/python:/app/factories/evaluation-factory/python:/app/factories/prompt-factory/python:/app/factories/workflow-factory/python:/app/layla/python"

# The base image installs only what run_production.py's own generic
# reference entrypoint actually needs at runtime: the real `anthropic`
# SDK for avishkar_router's AnthropicProvider (lazily imported -- see
# that module's own docstring), used only if a real ANTHROPIC_API_KEY
# is supplied at `docker run` time. Optional per-capability extras
# (voice, vision, computer_control, channels, mqtt, environment -- see
# layla/python/pyproject.toml) are deliberately NOT installed here; a
# deployment that needs one of those builds its own image FROM this
# one and adds the extra it actually needs.
RUN pip install --no-cache-dir anthropic

ENV LAYLA_DATA_DIR=/data/layla \
    LAYLA_HEALTH_HOST=0.0.0.0 \
    LAYLA_HEALTH_PORT=8080 \
    LAYLA_LOG_LEVEL=INFO

RUN mkdir -p /data/layla
VOLUME ["/data/layla"]
EXPOSE 8080

# A real health check against HealthServer's real /health endpoint
# (avishkar_layla.deployment) -- not a fabricated "process still
# running" liveness proxy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('LAYLA_HEALTH_PORT','8080') + '/health', timeout=3).status == 200 else 1)"

CMD ["python", "layla/deploy/run_production.py"]
