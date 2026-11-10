# Rucher Austral

Boutique mono-produit (miel de Manuka Oregan MGO 1650+). Pas de paiement en ligne :
le client envoie une **demande de commande**, reçue par e-mail.

## Installer / mettre à jour (instance OVH)

    cd ~/rucher-austral && git pull && sudo PORT=8080 bash deploy.sh

## Régler l'envoi des e-mails (une seule fois)

    sudo nano /etc/rucher-austral.env
    sudo systemctl restart rucher-austral-api

Renseigner SMTP_USER, SMTP_PASS (mot de passe d'application Gmail) et MAIL_TO.

## Vérifier

    curl -s http://127.0.0.1:8081/api/sante
    sudo journalctl -u rucher-austral-api -n 20
