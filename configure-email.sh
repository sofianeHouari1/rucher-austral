#!/usr/bin/env bash
# Assistant de configuration des e-mails de la boutique Rucher Austral.
# Usage : sudo bash configure-email.sh
set -euo pipefail
ENVFILE=/etc/rucher-austral.env

if [ "$(id -u)" -ne 0 ]; then echo "Lancez avec sudo : sudo bash configure-email.sh"; exit 1; fi

echo
echo "=== Réglage des e-mails de la boutique ==="
echo "Les demandes des clients seront envoyées à cette adresse Gmail."
echo "Elle n'est jamais visible sur le site."
echo

while true; do
  read -r -p "Adresse Gmail : " MAIL
  MAIL="$(echo "$MAIL" | tr -d '[:space:]')"
  [[ "$MAIL" =~ ^[^@]+@[^@]+\.[^@]+$ ]] && break
  echo "Adresse invalide, recommencez."
done

echo
echo "Clé de 16 lettres (mot de passe d'application Google) :"
echo "  compte Google > Sécurité > Validation en deux étapes > Mots de passe des applications"
echo "  (pas votre mot de passe Gmail habituel). Rien ne s'affiche quand vous collez, c'est normal."
while true; do
  read -r -s -p "Collez-le puis Entrée : " PASS; echo
  PASS="$(echo "$PASS" | tr -d '[:space:]')"
  [ ${#PASS} -eq 16 ] && break
  echo "Il faut exactement 16 lettres (vous en avez ${#PASS}). Recommencez."
done

echo
echo "Vérification auprès de Gmail..."
if ! PORT_OK=$(SMTP_USER="$MAIL" SMTP_PASS="$PASS" python3 - <<'PY'
import os, smtplib, socket, ssl, sys
_orig = socket.getaddrinfo
socket.getaddrinfo = lambda h, p, f=0, *a, **k: _orig(h, p, socket.AF_INET, *a, **k)  # IPv4 uniquement
user, pw = os.environ["SMTP_USER"], os.environ["SMTP_PASS"]
ctx = ssl.create_default_context()
erreurs = []
for port in (587, 465):
    try:
        if port == 465:
            s = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=15)
        else:
            s = smtplib.SMTP("smtp.gmail.com", 587, timeout=15); s.starttls(context=ctx)
        with s:
            s.login(user, pw)
        print(port); sys.exit(0)
    except smtplib.SMTPAuthenticationError:
        print("Gmail refuse l'adresse ou la clé de 16 lettres.", file=sys.stderr); sys.exit(1)
    except Exception as e:
        erreurs.append(f"port {port} : {e}")
print("Connexion à Gmail impossible (" + " ; ".join(erreurs) + ")", file=sys.stderr)
sys.exit(1)
PY
); then
  echo "Rien n'a été modifié. Relancez : sudo bash configure-email.sh"
  exit 1
fi
echo "Connexion à Gmail réussie (port $PORT_OK)."

umask 077
cat > "$ENVFILE" <<ENV
SMTP_HOST=smtp.gmail.com
SMTP_PORT=$PORT_OK
SMTP_USER=$MAIL
SMTP_PASS=$PASS
MAIL_TO=$MAIL
MAIL_FROM=
SHOP_NAME=Rucher Austral
ENV
chmod 600 "$ENVFILE"
unset PASS

systemctl restart rucher-austral-api
sleep 1
if curl -s http://127.0.0.1:8081/api/sante | grep -q '"email_configure": true'; then
  echo
  echo "C'est prêt. Les demandes de réservation arriveront sur $MAIL."
  echo "Faites une demande test depuis le site pour vérifier (pensez aux spams)."
else
  echo "Réglages enregistrés, mais le service ne répond pas. Envoyez le résultat de :"
  echo "  sudo journalctl -u rucher-austral-api -n 20"
fi
