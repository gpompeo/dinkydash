# Development container for the Ralph loop (scripts/ralph/ralph.sh).
#
# It holds Python, the pinned requirements and the Claude Code and GitHub CLIs, so an unattended
# run works in a throwaway filesystem: only the repository checkout is mounted into it. The
# requirements are baked in at /opt/venv, so rebuild when a requirements file changes (ralph.sh
# rebuilds on every start; the layers are cached).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates gnupg nodejs npm \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends gh \
 && npm install -g @anthropic-ai/claude-code \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/requirements
COPY requirements.txt requirements-dev.txt requirements-site.txt requirements-cloud.txt ./
RUN python -m venv /opt/venv \
 && pip install --no-cache-dir -r requirements-dev.txt -r requirements-cloud.txt

WORKDIR /workspace
