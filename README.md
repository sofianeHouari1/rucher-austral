# Manuka

Boutique mono-produit (miel de Manuka Oregan MGO 1650+). Pas de paiement en ligne :
le client envoie une **demande de commande**, reçue par e-mail.

## Installer / mettre à jour (instance OVH)

    cd ~/rucher-austral && git pull && sudo PORT=8080 bash deploy.sh

## Régler l'envoi des e-mails (une seule fois)

    sudo bash configure-email.sh

L'assistant demande l'adresse Gmail et le mot de passe d'application, vérifie la connexion, puis enregistre.

## Vérifier

    curl -s http://127.0.0.1:8081/api/sante
    sudo journalctl -u rucher-austral-api -n 20
