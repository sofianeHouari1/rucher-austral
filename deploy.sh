#!/usr/bin/env bash
# Installe la boutique Rucher Austral sur une instance OVH (Ubuntu/Debian).
# Usage : sudo ./deploy.sh                 -> accessible en http://IP
#         sudo PORT=8080 ./deploy.sh       -> sur un autre port si le 80 est déjà pris
#         sudo ./deploy.sh mondomaine.be    -> + certificat HTTPS Let's Encrypt
set -euo pipefail
DOMAIN="${1:-}"
PORT="${PORT:-80}"
WEBROOT=/var/www/rucher-austral

apt-get update -y
apt-get install -y nginx
mkdir -p "$WEBROOT"
install -m 644 "$(dirname "$0")/index.html" "$WEBROOT/index.html"

cat > /etc/nginx/sites-available/rucher-austral <<CONF
server {
    listen $PORT;
    listen [::]:$PORT;
    server_name ${DOMAIN:-_};
    root $WEBROOT;
    index index.html;
    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy strict-origin-when-cross-origin;
    gzip on;
    gzip_types text/css application/javascript;
    location / { try_files \$uri \$uri/ /index.html; }
}
CONF
ln -sf /etc/nginx/sites-available/rucher-austral /etc/nginx/sites-enabled/rucher-austral
rm -f /etc/nginx/sites-enabled/default
nginx -t
if ! systemctl restart nginx; then
  echo "Nginx ne démarre pas. Port $PORT occupé par :"
  ss -ltnp | grep ":$PORT " || true
  echo "Relancez avec un autre port : sudo PORT=8080 bash deploy.sh"
  exit 1
fi
systemctl enable nginx >/dev/null 2>&1 || true

# Pare-feu (si ufw est présent)
if command -v ufw >/dev/null; then ufw allow OpenSSH; ufw allow "$PORT"/tcp; ufw allow 'Nginx Full'; fi

if [ -n "$DOMAIN" ]; then
  apt-get install -y certbot python3-certbot-nginx
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect
  echo "En ligne : https://$DOMAIN"
else
  echo "En ligne : http://$(curl -s -4 ifconfig.me || hostname -I | awk '{print $1}'):$PORT"
fi
