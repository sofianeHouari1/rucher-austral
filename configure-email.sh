#!/usr/bin/env bash
# Assistant de configuration des e-mails de la boutique Rucher Austral (via Resend, en HTTPS).
# L'instance OVH bloque l'envoi SMTP sortant : on passe par l'API HTTPS de Resend.
# Usage : sudo bash configure-email.sh
set -euo pipefail
ENVFILE=/etc/rucher-austral.env

if [ "$(id -u)" -ne 0 ]; then echo "Lancez avec sudo : sudo bash configure-email.sh"; exit 1; fi

echo
echo "=== Réglage des e-mails de la boutique ==="
echo "Les demandes des clients seront envoyées à votre adresse."
echo "Elle n'est jamais visible sur le site."
echo

while true; do
  read -r -p "Adresse qui reçoit les demandes (celle de votre compte Resend) : " MAIL
  MAIL="$(echo "$MAIL" | tr -d '[:space:]')"
  [[ "$MAIL" =~ ^[^@]+@[^@]+\.[^@]+$ ]] && break
  echo "Adresse invalide, recommencez."
done

echo
echo "Clé API Resend (elle commence par re_)."
echo "  resend.com > API Keys > Create API Key. Rien ne s'affiche quand vous collez, c'est normal."
while true; do
  read -r -s -p "Collez-la puis Entrée : " KEY; echo
  KEY="$(echo "$KEY" | tr -d '[:space:]')"
  [[ "$KEY" == re_* && ${#KEY} -gt 10 ]] && break
  echo "Ce n'est pas une clé Resend (elle doit commencer par re_). Recommencez."
done

echo
echo "Envoi d'un e-mail de test à $MAIL..."
if ! RESEND_API_KEY="$KEY" MAIL_TO="$MAIL" python3 - <<'PY'
import json, os, socket, sys, urllib.error, urllib.request
_orig = socket.getaddrinfo
socket.getaddrinfo = lambda h, p, f=0, *a, **k: _orig(h, p, socket.AF_INET, *a, **k)  # IPv4
corps = {
    "from": "Rucher Austral <onboarding@resend.dev>",
    "to": [os.environ["MAIL_TO"]],
    "subject": "Rucher Austral : e-mails de réservation activés",
    "text": "Ce message confirme que les demandes de réservation du site arriveront sur cette adresse.",
}
req = urllib.request.Request("https://api.resend.com/emails", data=json.dumps(corps).encode(),
    headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
             "Content-Type": "application/json", "User-Agent": "rucher-austral/1.0"}, method="POST")
try:
    urllib.request.urlopen(req, timeout=20).read()
except urllib.error.HTTPError as e:
    detail = e.read().decode(errors="replace")[:300]
    if e.code in (401, 403) and "testing emails" in detail:
        print("Resend n'accepte que l'adresse de votre compte Resend : utilisez celle-là.")
    elif e.code in (401, 403):
        print("Resend refuse la clé :", detail)
    else:
        print(f"Erreur Resend {e.code} :", detail)
    sys.exit(1)
except Exception as e:
    print("Connexion à Resend impossible :", e)
    sys.exit(1)
PY
then
  echo "Rien n'a été modifié. Relancez : sudo bash configure-email.sh"
  exit 1
fi

umask 077
cat > "$ENVFILE" <<ENV
RESEND_API_KEY=$KEY
MAIL_TO=$MAIL
MAIL_FROM=onboarding@resend.dev
SHOP_NAME=Rucher Austral
ENV
chmod 600 "$ENVFILE"
unset KEY

systemctl restart rucher-austral-api
sleep 1
if curl -s http://127.0.0.1:8081/api/sante | grep -q '"email_configure": true'; then
  echo
  echo "C'est prêt. Un e-mail de test vient d'être envoyé à $MAIL (regardez aussi les spams)."
  echo "Les demandes de réservation arriveront à cette adresse."
else
  echo "Réglages enregistrés, mais le service ne répond pas. Envoyez le résultat de :"
  echo "  sudo journalctl -u rucher-austral-api -n 20"
fi
