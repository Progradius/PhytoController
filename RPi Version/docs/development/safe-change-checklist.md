# Checklist de changement sûr

## Tout changement

- [ ] Périmètre et comportement attendu décrits
- [ ] État Git initial examiné, changements utilisateur préservés
- [ ] Aucun secret dans diff, logs ou artefacts
- [ ] Configuration compatible ou migration fournie
- [ ] Erreurs et rollback décrits
- [ ] Documentation et risques mis à jour
- [ ] `python3 -m pytest` sans échec
- [ ] `diff -u CLAUDE.md AGENTS.md` vide
- [ ] `git diff --check` sans erreur

## GPIO, relais, moteur ou chauffage

- [ ] BCM et numéro physique vérifiés
- [ ] Propriétaire unique et absence de collision
- [ ] Fonction alternative et pull au boot vérifiés
- [ ] Polarité active-BAS/active-HAUT explicitée
- [ ] État sûr boot, nominal, exception, annulation et arrêt décrit
- [ ] Aucune utilisation de `GPIO.cleanup()`
- [ ] ON/attente/OFF protégé par `energized()`
- [ ] Plusieurs vitesses moteur impossibles ou coupées
- [ ] Test sans charge, relais seul puis charge planifié
- [ ] Protocole `docs/development/hardware-validation.md` suivi et preuve consignée
- [ ] Lecture physique des GPIO avant/après arrêt
- [ ] Protection matérielle indépendante vérifiée

## Boucle asyncio

- [ ] Fabrique de coroutine réutilisable
- [ ] Enregistrement auprès du superviseur
- [ ] `safe_state` pour toute sortie
- [ ] Heartbeat par tour et sommeil supervisé
- [ ] Annulation propagée correctement
- [ ] I/O bloquante absente ou isolée avec timeout
- [ ] Exception injectée et relance observée

## Configuration

- [ ] Candidat revalidé intégralement
- [ ] Contraintes simples et croisées présentes
- [ ] Écriture atomique conservée
- [ ] Booléens legacy sérialisés si nécessaire
- [ ] Champ classé secret/non secret et chaud/redémarrage
- [ ] Configuration ancienne migrée sur copie
- [ ] Valeur invalide refusée sans modifier le contrôle actif

## HTTP

- [ ] GET sans effet de bord
- [ ] Méthode et codes documentés
- [ ] Taille et timeout bornés
- [ ] Chemin confiné
- [ ] Auth/Origin/Host et hypothèse réseau évalués
- [ ] Aucune donnée sensible dans réponse ou log
- [ ] Liveness et readiness non confondues

## Preuve de fin

- [ ] Lecture du code
- [ ] Vérification syntaxique proportionnée
- [ ] Suite `pytest` exécutée, test de régression ajouté si le contrat change
- [ ] Vérification sur Pi si matériel concerné
- [ ] Commit déployé identifié
- [ ] Résultat et limites résiduelles consignés
