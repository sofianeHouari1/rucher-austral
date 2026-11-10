RUCHER AUSTRAL — déploiement sur instance OVH

Depuis votre ordinateur (remplacez IP par l'IP de l'instance, ubuntu par l'utilisateur si différent) :

  unzip rucher-austral.zip
  scp -r rucher-austral ubuntu@IP:~
  ssh ubuntu@IP "cd rucher-austral && sudo ./deploy.sh"

Avec un nom de domaine (enregistrement A pointant d'abord vers l'IP) :

  ssh ubuntu@IP "cd rucher-austral && sudo ./deploy.sh mondomaine.be"

Mise à jour du site plus tard :

  scp rucher-austral/index.html ubuntu@IP:/tmp/ && ssh ubuntu@IP "sudo cp /tmp/index.html /var/www/rucher-austral/"
