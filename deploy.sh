#!/usr/bin/env bash
# Installe la boutique Manuka sur une instance OVH (Ubuntu/Debian).
# Usage : sudo bash deploy.sh                 -> accessible en http://IP
#         sudo PORT=8080 bash deploy.sh       -> sur un autre port si le 80 est déjà pris
#         sudo bash deploy.sh mondomaine.be   -> + certificat HTTPS Let's Encrypt (port 80 libre requis)
set -euo pipefail
DOMAIN="${1:-}"
PORT="${PORT:-80}"
SRC="$(cd "$(dirname "$0")" && pwd)"
WEBROOT=/var/www/rucher-austral
APPDIR=/opt/rucher-austral
ENVFILE=/etc/rucher-austral.env

apt-get update -y
apt-get install -y nginx python3

# 1. Site
mkdir -p "$WEBROOT"
install -m 644 "$SRC/index.html" "$WEBROOT/index.html"
install -m 644 "$SRC/manuka-recolte.mp4" "$SRC/manuka-poster.jpg" "$WEBROOT/"

# 2. API des demandes de commande (envoi d'e-mail)
mkdir -p "$APPDIR"
install -m 755 "$SRC/api/server.py" "$APPDIR/server.py"

if [ ! -f "$ENVFILE" ]; then
  cat > "$ENVFILE" <<'ENV'
# Réglages e-mail de la boutique. Après modification : sudo systemctl restart rucher-austral-api
# Gmail : SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_PASS = mot de passe d'application
#         (compte Google > Sécurité > Validation en deux étapes > Mots de passe des applications)
# OVH Mail : SMTP_HOST=ssl0.ovh.net, SMTP_PORT=465
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
# Adresse qui reçoit les demandes (jamais visible par les clients)
MAIL_TO=
# Expéditeur (laisser vide = SMTP_USER)
MAIL_FROM=
SHOP_NAME=Manuka
ENV
  chmod 600 "$ENVFILE"
  echo "Fichier de réglages e-mail créé : $ENVFILE (à compléter)"
fi

cat > /etc/systemd/system/rucher-austral-api.service <<UNIT
[Unit]
Description=Manuka - demandes de commande par e-mail
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=$ENVFILE
ExecStart=/usr/bin/python3 $APPDIR/server.py
Restart=always
RestartSec=3
DynamicUser=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable rucher-austral-api >/dev/null 2>&1
systemctl restart rucher-austral-api

# 3. Nginx
cat > /etc/nginx/sites-available/rucher-austral <<CONF
server {
    listen $PORT;
    listen [::]:$PORT;
    server_name ${DOMAIN:-_};
    root $WEBROOT;
    index index.html;
    client_max_body_size 16k;
    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy strict-origin-when-cross-origin;
    gzip on;
    gzip_types text/css application/javascript application/json;
    location ~* \.(mp4|jpg)$ { add_header Cache-Control "public, max-age=604800"; }

    location /api/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$http_x_forwarded_for;
    }
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

sleep 1
if curl -s http://127.0.0.1:8081/api/sante | grep -q '"email_configure": true'; then
  echo "E-mails de commande : configurés."
else
  echo "E-mails de commande : PAS ENCORE configurés. Lancez : sudo bash configure-email.sh"
fi
