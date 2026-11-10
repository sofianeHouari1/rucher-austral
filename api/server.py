#!/usr/bin/env python3
"""Manuka - reçoit les demandes de réservation et les envoie par e-mail.

Écoute sur 127.0.0.1:8081, derrière Nginx (/api/commande).
Configuration : /etc/rucher-austral.env (voir deploy.sh).
Aucune dépendance : bibliothèque standard Python uniquement.
"""
import json
import os
import re
import smtplib
import socket
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

# L'instance n'a pas de route IPv6 : on force l'IPv4 pour joindre le serveur SMTP.
_getaddrinfo = socket.getaddrinfo
socket.getaddrinfo = lambda h, p, f=0, *a, **k: _getaddrinfo(h, p, socket.AF_INET, *a, **k)

# Prix fixé côté serveur : le navigateur n'envoie que la quantité.
PRODUIT = "Miel de Manuka Oregan MGO 1650+ (500 g)"
PRIX = 190.00
QTE_MAX = 10

CFG = {k: os.environ.get(k, "") for k in (
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_FROM", "MAIL_TO", "SHOP_NAME", "RESEND_API_KEY")}
CFG["SMTP_PORT"] = int(CFG["SMTP_PORT"] or 587)
CFG["SHOP_NAME"] = CFG["SHOP_NAME"] or "Manuka"
CFG["MAIL_FROM"] = CFG["MAIL_FROM"] or CFG["SMTP_USER"] or "onboarding@resend.dev"


def email_configure():
    if not CFG["MAIL_TO"]:
        return False
    return bool(CFG["RESEND_API_KEY"]) or all(CFG[k] for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"))


def envoyer_resend(msg):
    """Envoi via l'API HTTPS de Resend (utile quand l'hébergeur bloque le SMTP)."""
    corps = {
        "from": msg["From"],
        "to": [CFG["MAIL_TO"]],
        "subject": str(msg["Subject"]),
        "text": msg.get_content(),
    }
    if msg["Reply-To"]:
        corps["reply_to"] = str(msg["Reply-To"])
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(corps).encode(),
        headers={"Authorization": "Bearer " + CFG["RESEND_API_KEY"],
                 "Content-Type": "application/json",
                 "User-Agent": "manuka/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Resend {e.code} : {e.read().decode(errors='replace')[:300]}")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LIMITES = {"prenom": 60, "nom": 60, "email": 150, "telephone": 40, "adresse": 200,
           "code_postal": 12, "ville": 100, "pays": 60, "message": 1000, "langue": 5}
OBLIGATOIRES = ("prenom", "nom", "email", "adresse", "code_postal", "ville", "pays")
_historique = {}  # ip -> horodatages des demandes récentes


def trop_de_demandes(ip, maxi=5, fenetre=600):
    now = time.time()
    recents = [t for t in _historique.get(ip, []) if now - t < fenetre]
    _historique[ip] = recents
    if len(recents) >= maxi:
        return True
    recents.append(now)
    return False


def eur(x):
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


def envoyer(msg):
    if CFG["RESEND_API_KEY"]:
        return envoyer_resend(msg)
    if CFG["SMTP_PORT"] == 465:
        with smtplib.SMTP_SSL(CFG["SMTP_HOST"], 465, context=ssl.create_default_context(), timeout=20) as s:
            s.login(CFG["SMTP_USER"], CFG["SMTP_PASS"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(CFG["SMTP_HOST"], CFG["SMTP_PORT"], timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(CFG["SMTP_USER"], CFG["SMTP_PASS"])
            s.send_message(msg)


def traiter(d):
    c = {k: " ".join(str(d.get(k, "")).split())[:n] for k, n in LIMITES.items()}
    c["message"] = str(d.get("message", "")).strip()[:LIMITES["message"]]
    if any(not c[k] for k in OBLIGATOIRES):
        return 400, {"erreur": "Complétez les champs obligatoires."}
    if not EMAIL_RE.match(c["email"]):
        return 400, {"erreur": "L'adresse e-mail n'est pas valide."}
    try:
        qte = int(d.get("quantite", 0))
    except (TypeError, ValueError):
        qte = 0
    if not 1 <= qte <= QTE_MAX:
        return 400, {"erreur": "Quantité invalide."}

    total = qte * PRIX
    maintenant = datetime.now(ZoneInfo("Europe/Brussels"))
    numero = "MK-" + maintenant.strftime("%y%m%d-%H%M%S")
    client = f"{c['prenom']} {c['nom']}"
    langue = {"fr": "français", "nl": "néerlandais", "en": "anglais"}.get(c["langue"], "français")

    msg = EmailMessage()
    msg["Subject"] = f"Demande de réservation {numero} - {client} - {qte} pot{'s' if qte > 1 else ''}"
    msg["From"] = formataddr((CFG["SHOP_NAME"], CFG["MAIL_FROM"]))
    msg["To"] = CFG["MAIL_TO"]
    msg["Reply-To"] = formataddr((client, c["email"]))
    msg["Message-ID"] = make_msgid(domain="rucher-austral")
    msg.set_content(
        f"Demande {numero} reçue le {maintenant.strftime('%d/%m/%Y à %H:%M')}\n\n"
        f"Quantité demandée : {qte} × {PRODUIT}\n"
        f"Montant indicatif : {eur(total)} (hors livraison)\n\n"
        f"Client\n"
        f"  Prénom : {c['prenom']}\n"
        f"  Nom : {c['nom']}\n"
        f"  E-mail : {c['email']}\n"
        f"  Téléphone : {c['telephone'] or '-'}\n"
        f"  Adresse : {c['adresse']}\n"
        f"            {c['code_postal']} {c['ville']}\n"
        f"            {c['pays']}\n\n"
        f"  Langue du site : {langue}\n\n"
        f"Message :\n{c['message'] or '-'}\n\n"
        f"Répondez à cet e-mail pour écrire directement au client.\n"
    )
    envoyer(msg)
    print(f"Demande {numero} envoyée ({qte} pot(s))", flush=True)
    return 200, {"ok": True, "numero": numero}


class Handler(BaseHTTPRequestHandler):
    server_version = "Manuka"

    def repondre(self, code, data):
        corps = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        if self.path == "/api/sante":
            return self.repondre(200, {"ok": True, "email_configure": email_configure()})
        self.repondre(404, {"erreur": "Introuvable."})

    def do_POST(self):
        if self.path != "/api/commande":
            return self.repondre(404, {"erreur": "Introuvable."})
        ip = self.headers.get("X-Real-IP") or self.client_address[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 10_000:
            return self.repondre(400, {"erreur": "Demande invalide."})
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(d, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self.repondre(400, {"erreur": "Demande invalide."})
        if d.get("website"):  # champ piège anti-robots
            return self.repondre(200, {"ok": True, "numero": "MK-0"})
        if trop_de_demandes(ip):
            return self.repondre(429, {"erreur": "Trop de demandes. Réessayez dans quelques minutes."})
        if not email_configure():
            print("E-mail non configuré : complétez /etc/rucher-austral.env", flush=True)
            return self.repondre(503, {"erreur": "Les commandes sont momentanément indisponibles."})
        try:
            code, data = traiter(d)
        except Exception as e:
            print("Erreur d'envoi :", repr(e), flush=True)
            code, data = 502, {"erreur": "L'envoi de la demande a échoué."}
        self.repondre(code, data)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print("API Manuka sur 127.0.0.1:8081", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8081), Handler).serve_forever()
