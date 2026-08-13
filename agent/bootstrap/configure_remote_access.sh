#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ACCESS_MODE="${MITIGATE_ACCESS_MODE:-local}"
ACCESS_HOST="${MITIGATE_ACCESS_HOST:-}"
ACCESS_USERNAME="${MITIGATE_ACCESS_USERNAME:-admin}"
CANVAS_UPSTREAM="${MITIGATE_CANVAS_UPSTREAM:-http://127.0.0.1:8000}"
NGINX_SITE="${MITIGATE_NGINX_EXISTING_SITE:-/etc/nginx/sites-available/mitigate}"

log() {
    printf '\n[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ "$EUID" -eq 0 ]] || die "Run this script with sudo."

case "$ACCESS_MODE" in
    local)
        log "Local-only access selected."
        exit 0
        ;;
    ip|domain)
        ;;
    *)
        die "MITIGATE_ACCESS_MODE must be local, ip, or domain."
        ;;
esac

[[ -n "$ACCESS_HOST" ]] || die "MITIGATE_ACCESS_HOST is required."

log "Installing prerequisites"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    nginx \
    apache2-utils \
    snapd \
    ca-certificates \
    curl

systemctl enable --now nginx

log "Installing current Certbot"

if snap list certbot >/dev/null 2>&1; then
    snap refresh certbot || true
else
    snap install --classic certbot
fi

ln -sfn /snap/bin/certbot /usr/local/bin/certbot
certbot --version

log "Configuring username/password protection"

HTPASSWD_FILE="/etc/nginx/.mitigate-ai.htpasswd"

if [[ -n "${MITIGATE_ACCESS_PASSWORD:-}" ]]; then
    printf '%s\n' "$MITIGATE_ACCESS_PASSWORD" \
        | htpasswd -i -c "$HTPASSWD_FILE" "$ACCESS_USERNAME"
elif [[ ! -f "$HTPASSWD_FILE" ]]; then
    echo
    echo "Create password for user: $ACCESS_USERNAME"
    htpasswd -c "$HTPASSWD_FILE" "$ACCESS_USERNAME"
else
    log "Existing authentication file preserved."
fi

chown root:www-data "$HTPASSWD_FILE"
chmod 640 "$HTPASSWD_FILE"

log "Preparing ACME challenge"

install -d -m 0755 -o www-data -g www-data /var/www/letsencrypt
[[ -f "$NGINX_SITE" ]] || die "Existing nginx site not found: $NGINX_SITE"

if ! grep -q 'MITIGATE_AI_ACME_CHALLENGE' "$NGINX_SITE"; then
    python3 - "$NGINX_SITE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
marker = "    location / {\n"
block = """    # MITIGATE_AI_ACME_CHALLENGE
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type text/plain;
        try_files $uri =404;
    }

"""
if marker not in text:
    raise SystemExit("ERROR: nginx location marker not found")
path.write_text(text.replace(marker, block + marker, 1))
PY
fi

nginx -t
systemctl reload nginx

log "Requesting HTTPS certificate"

if [[ "$ACCESS_MODE" == "ip" ]]; then
    certbot certonly \
        --non-interactive \
        --agree-tos \
        --register-unsafely-without-email \
        --preferred-profile shortlived \
        --webroot \
        --webroot-path /var/www/letsencrypt \
        --ip-address "$ACCESS_HOST"
else
    certbot certonly \
        --non-interactive \
        --agree-tos \
        --register-unsafely-without-email \
        --webroot \
        --webroot-path /var/www/letsencrypt \
        -d "$ACCESS_HOST"
fi

CERT_DIR="/etc/letsencrypt/live/${ACCESS_HOST}"
[[ -f "$CERT_DIR/fullchain.pem" ]] || die "Certificate was not created."
[[ -f "$CERT_DIR/privkey.pem" ]] || die "Certificate private key was not created."

log "Creating HTTPS reverse proxy"

cat > /etc/nginx/sites-available/mitigate-ai-access <<EOF_NGINX
server {
    listen 443 ssl;
    listen [::]:443 ssl;

    server_name ${ACCESS_HOST};

    ssl_certificate ${CERT_DIR}/fullchain.pem;
    ssl_certificate_key ${CERT_DIR}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 128M;

    auth_basic "MITIGATE AI";
    auth_basic_user_file /etc/nginx/.mitigate-ai.htpasswd;

    access_log /var/log/nginx/mitigate_ai_access.log;
    error_log /var/log/nginx/mitigate_ai_error.log;

    location / {
        proxy_pass ${CANVAS_UPSTREAM};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }
}
EOF_NGINX

ln -sfn /etc/nginx/sites-available/mitigate-ai-access /etc/nginx/sites-enabled/mitigate-ai-access
nginx -t
systemctl reload nginx

log "Installing automatic certificate reload hook"

install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/mitigate-ai-nginx-reload.sh <<'EOF_HOOK'
#!/usr/bin/env bash
set -euo pipefail
/usr/sbin/nginx -t
/bin/systemctl reload nginx
EOF_HOOK
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/mitigate-ai-nginx-reload.sh

log "Final verification"
curl -fsS --max-time 10 http://127.0.0.1:8000/ready
echo
nginx -t
ss -ltnp | grep ':443' || die "HTTPS port 443 is not listening."

echo
echo "=================================================="
echo "MITIGATE AI REMOTE ACCESS READY"
echo "=================================================="
echo "Mode:     $ACCESS_MODE"
echo "Host:     $ACCESS_HOST"
echo "Username: $ACCESS_USERNAME"
echo "URL:      https://${ACCESS_HOST}/canvas"
echo "Backend:  $CANVAS_UPSTREAM"
