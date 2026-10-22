#!/bin/bash
# Run on tv-mum-01 as root after copying layla365-src.tgz to /tmp.
set -euo pipefail
APP=/opt/layla365/app
id l365 >/dev/null 2>&1 || useradd -r -m -d /home/l365 -s /usr/sbin/nologin l365
mkdir -p $APP && tar -xzf /tmp/layla365-src.tgz -C $APP
apt-get install -y python3-venv >/dev/null 2>&1
[ -d /opt/layla365/venv ] || python3 -m venv /opt/layla365/venv
/opt/layla365/venv/bin/pip install -q --upgrade pip
/opt/layla365/venv/bin/pip install -q psycopg2-binary PyYAML

# runner.env = data secrets (+ llm secrets if present); readable only by l365
set -a; . /opt/layla365/secrets/data.env; set +a
{
  grep -E '^(PGPASS_|QDRANT_API_KEY)' /opt/layla365/secrets/data.env
  [ -f /opt/layla365/secrets/llm.env ] && cat /opt/layla365/secrets/llm.env || true
  echo "L365_ROOT=$APP"
} > /opt/layla365/secrets/runner.env
chown l365:l365 /opt/layla365/secrets/runner.env && chmod 600 /opt/layla365/secrets/runner.env
chown -R l365:l365 $APP /opt/layla365/venv

# schema (idempotent)
docker exec -i l365-postgres psql -v ON_ERROR_STOP=1 -q -U "$PG_SUPERUSER" -d layla365 < $APP/sql/001_core.sql
echo "core schema applied"

install -m 644 $APP/deploy/l365-runner.service /etc/systemd/system/l365-runner.service
systemctl daemon-reload
echo "installed (service not started yet)"
