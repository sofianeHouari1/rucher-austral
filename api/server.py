#!/usr/bin/env python3
"""Rucher Austral - reçoit les demandes de commande et les envoie par e-mail.

Écoute sur 127.0.0.1:8081, derrière Nginx (/api/commande).
Configuration : /etc/rucher-austral.env (voir deploy.sh).
Aucune dépendance : bibliothèque standard Python uniquement.
"""
import json
import os
import re
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

# Prix fixés côté serveur : le navigateur n'envoie que la quantité.
PRODUIT = "Miel de Manuka Oregan MGO 1650+ (500 g)"
PRIX = 190.00
LIVRAISON = 6.90
LIVRAISON_OFFERTE_DES = 150.00
QTE_MAX = 10

CFG = {k: os.environ.get(k, "") for k in (
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_FROM", "MAIL_TO", "SHOP_NAME")}
CFG["SMTP_PORT"] = int(CFG["SMTP_PORT"] or 587)
CFG["SHOP_NAME"] = CFG["SHOP_NAME"] or "Rucher Austral"
CFG["MAIL_FROM"] = CFG["MAIL_FROM"] or CFG["SMTP_USER"]
CONFIRMATION_CLIENT = os.environ.get("CONFIRMATION_CLIENT", "1") == "1"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LIMITES = {"nom": 100, "email": 150, "telephone": 40, "adresse": 200,
           "code_postal": 12, "ville": 100, "message": 1000}
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
    champs = {k: " ".join(str(d.get(k, "")).split())[:n] for k, n in LIMITES.items()}
    champs["message"] = str(d.get("message", "")).strip()[:LIMITES["message"]]
    for k in ("nom", "email", "adresse", "code_postal", "ville"):
        if not champs[k]:
            return 400, {"erreur": "Complétez les champs obligatoires."}
    if not EMAIL_RE.match(champs["email"]):
        return 400, {"erreur": "L'adresse e-mail n'est pas valide."}
    try:
        qte = int(d.get("quantite", 0))
    except (TypeError, ValueError):
        qte = 0
    if not 1 <= qte <= QTE_MAX:
        return 400, {"erreur": "Quantité invalide."}

    sous_total = qte * PRIX
    port = 0.0 if sous_total >= LIVRAISON_OFFERTE_DES else LIVRAISON
    total = sous_total + port
    maintenant = datetime.now(ZoneInfo("Europe/Brussels"))
    numero = "RA-" + maintenant.strftime("%y%m%d-%H%M%S")

    recap = (
        f"{qte} × {PRODUIT} à {eur(PRIX)}\n"
        f"Sous-total : {eur(sous_total)}\n"
        f"Livraison (Belgique) : {'offerte' if port == 0 else eur(port)}\n"
        f"Total estimé : {eur(total)}\n"
    )

    vendeur = EmailMessage()
    vendeur["Subject"] = f"Nouvelle demande de commande {numero} - {champs['nom']} - {eur(total)}"
    vendeur["From"] = formataddr((CFG["SHOP_NAME"], CFG["MAIL_FROM"]))
    vendeur["To"] = CFG["MAIL_TO"]
    vendeur["Reply-To"] = formataddr((champs["nom"], champs["email"]))
    vendeur["Message-ID"] = make_msgid(domain="rucher-austral")
    vendeur.set_content(
        f"Demande {numero} reçue le {maintenant.strftime('%d/%m/%Y à %H:%M')}\n\n"
        f"{recap}\n"
        f"Client\n"
        f"  Nom : {champs['nom']}\n"
        f"  E-mail : {champs['email']}\n"
        f"  Téléphone : {champs['telephone'] or '-'}\n"
        f"  Adresse : {champs['adresse']}, {champs['code_postal']} {champs['ville']}\n\n"
        f"Message :\n{champs['message'] or '-'}\n\n"
        f"Répondez directement à cet e-mail pour écrire au client.\n"
    )
    envoyer(vendeur)

    if CONFIRMATION_CLIENT:
        client = EmailMessage()
        client["Subject"] = f"Votre demande de commande {numero} - {CFG['SHOP_NAME']}"
        client["From"] = formataddr((CFG["SHOP_NAME"], CFG["MAIL_FROM"]))
        client["To"] = champs["email"]
        client["Reply-To"] = CFG["MAIL_TO"]
        client.set_content(
            f"Bonjour {champs['nom']},\n\n"
            f"Nous avons bien reçu votre demande de commande {numero} :\n\n{recap}\n"
            f"Livraison prévue à : {champs['adresse']}, {champs['code_postal']} {champs['ville']}\n\n"
            f"Aucun paiement n'a été effectué. Nous revenons vers vous rapidement pour "
            f"confirmer la commande et les modalités de règlement.\n\n"
            f"{CFG['SHOP_NAME']}\n"
        )
        try:
            envoyer(client)
        except Exception as e:  # la demande est déjà arrivée chez le vendeur
            print("Confirmation client non envoyée :", e, flush=True)

    print(f"Demande {numero} envoyée ({qte} pot(s), {eur(total)})", flush=True)
    return 200, {"ok": True, "numero": numero, "total": round(total, 2)}


class Handler(BaseHTTPRequestHandler):
    server_version = "RucherAustral"

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
            pret = all(CFG[k] for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_TO"))
            return self.repondre(200, {"ok": True, "email_configure": pret})
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
            return self.repondre(200, {"ok": True, "numero": "RA-0", "total": 0})
        if trop_de_demandes(ip):
            return self.repondre(429, {"erreur": "Trop de demandes. Réessayez dans quelques minutes."})
        if not all(CFG[k] for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_TO")):
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
    print("API Rucher Austral sur 127.0.0.1:8081", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8081), Handler).serve_forever()
