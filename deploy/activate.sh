#!/usr/bin/env bash
# Run as root after unpacking the allowlisted bundle and installing dependencies.
set -euo pipefail
getent passwd shengban >/dev/null || useradd --system --home-dir /var/lib/shengban --shell /usr/sbin/nologin shengban
getent passwd caddy >/dev/null || useradd --system --home-dir /var/lib/caddy --shell /usr/sbin/nologin caddy
install -d -o shengban -g shengban -m 700 /var/lib/shengban /var/lib/shengban/jobs
install -d -o caddy -g caddy -m 700 /var/lib/caddy
install -d -m 755 /etc/caddy
install -m 644 /opt/shengban/deploy/Caddyfile /etc/caddy/Caddyfile
install -m 644 /opt/shengban/deploy/shengban-api.service /etc/systemd/system/
install -m 644 /opt/shengban/deploy/shengban-web.service /etc/systemd/system/
chmod -R a+rX /opt/shengban/app /opt/shengban/site
printf '%s\n' '{"enabled":true,"recognitionUrl":"/labs/recognition.html"}' > /opt/shengban/site/recognition-config.json
/usr/local/bin/caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl daemon-reload
systemctl enable --now shengban-api shengban-web
