# Déploiement

Cette page rassemble les points d'attention pour exploiter le backend en
production.

## Configuration de base

Variables à définir explicitement :

```env
DJANGO_SECRET_KEY=very-long-production-secret
POSTGRES_DB=godotgame
POSTGRES_USER=godotuser
POSTGRES_PASSWORD=strong-password
POSTGRES_HOST=database-host
POSTGRES_PORT=5432
GAME_API_WRITE_TOKEN=strong-bootstrap-token
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.org
```

Le projet est configuré avec :

- `DEBUG = False` ;
- `ALLOWED_HOSTS = ["alzheimer.magellan.fpms.ac.be"]` ;
- `WhiteNoise` pour les fichiers statiques ;
- cookies session et CSRF sécurisés ;
- redirection HTTPS activable via `DJANGO_SECURE_SSL_REDIRECT` ;
- HSTS activé par défaut en production.

Si le domaine change, mettre à jour `ALLOWED_HOSTS` dans `config/settings.py`.

## Base de données

Le backend utilise PostgreSQL.

Avant le premier démarrage :

```bash
python manage.py migrate
python manage.py createsuperuser
```

Pour les environnements managés qui imposent SSL, définir par exemple :

```env
POSTGRES_SSLMODE=require
```

## Fichiers statiques et médias

Les statiques Django sont collectés dans `STATIC_ROOT` :

```bash
python manage.py collectstatic
```

Les médias sont écrits dans `MEDIA_ROOT`, notamment :

- `media/seeds/` pour les fichiers de niveaux de référence ;
- `media/reports/full/` pour les rapports `.dat`.

Ces fichiers doivent être persistés entre les déploiements. Ne pas les stocker
uniquement dans un conteneur éphémère.

## Sécurité API

Points à surveiller :

- `GAME_API_WRITE_TOKEN` doit être long, secret et différent selon les
  environnements.
- Les access tokens expirent par défaut après 15 minutes.
- Les refresh tokens expirent par défaut après 30 jours.
- Les refresh tokens sont stockés sous forme de hash SHA-256.
- Les refresh tokens sont rotatifs : l'ancien token devient inutile après un
  rafraîchissement réussi.
- Les actions d'administration doivent passer par un compte Django `is_staff`.

## Administration

L'admin Django permet :

- de consulter les joueurs ;
- de consulter les médecins ;
- de consulter les seeds ;
- de télécharger les rapports `.dat` ;
- d'ouvrir le graphique PNG d'un rapport ;
- d'ouvrir les statistiques d'un rapport.

Créer au moins un compte administrateur :

```bash
python manage.py createsuperuser
```

## Vérification après déploiement

Checklist minimale :

- `python manage.py check`
- `python manage.py migrate --check`
- `python manage.py collectstatic --noinput`
- connexion à `/admin/`
- création d'une session via `/api/auth/token/`
- upload d'un petit rapport `.dat` de test ;
- accès staff à `/api/fullreport/stats/?format=json`.

## Sauvegardes

Sauvegarder ensemble :

- la base PostgreSQL ;
- le dossier `MEDIA_ROOT`.

Les rapports `.dat` et les seeds sont stockés sur disque, pas seulement en base.
Une sauvegarde uniquement SQL serait donc incomplète.

## Documentation statique

La documentation peut être générée ainsi :

```bash
pip install -r requirements-docs.txt
mkdocs build
```

Le rendu final est écrit dans `site/`. Ce dossier peut être servi par un serveur
statique ou publié dans une plateforme de documentation.
