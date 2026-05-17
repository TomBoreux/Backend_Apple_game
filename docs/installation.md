# Installation

## Prérequis

- Python compatible avec Django 4.2.
- PostgreSQL accessible depuis le backend.
- Un environnement virtuel Python.
- Les dépendances système nécessaires à `psycopg2-binary`, `matplotlib` et
  `numpy` selon l'environnement d'exécution.

## Installation locale

Depuis le dossier `backend_game` :

```bash
python -m venv ../venv
source ../venv/bin/activate
pip install -r requirements.txt
```

Créer ensuite un fichier `.env` à la racine du projet Django :

```env
DJANGO_SECRET_KEY=replace-with-a-long-secret
POSTGRES_DB=godotgame
POSTGRES_USER=godotuser
POSTGRES_PASSWORD=replace-me
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
GAME_API_WRITE_TOKEN=replace-with-a-client-bootstrap-token
```

Appliquer les migrations puis créer un administrateur :

```bash
python manage.py migrate
python manage.py createsuperuser
```

Lancer le serveur local :

```bash
python manage.py runserver
```

## Variables d'environnement

| Variable | Rôle | Valeur par défaut |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Clé secrète Django. Obligatoire. | Aucune |
| `POSTGRES_DB` | Nom de la base PostgreSQL. | `godotgame` |
| `POSTGRES_USER` | Utilisateur PostgreSQL. | `godotuser` |
| `POSTGRES_PASSWORD` | Mot de passe PostgreSQL. | Vide |
| `POSTGRES_HOST` | Hôte PostgreSQL. | `localhost` |
| `POSTGRES_PORT` | Port PostgreSQL. | `5432` |
| `POSTGRES_CONN_MAX_AGE` | Durée de conservation des connexions DB. | `60` |
| `POSTGRES_SSLMODE` | Mode SSL PostgreSQL si requis. | Vide |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origines CSRF autorisées, séparées par virgules. | Vide |
| `DJANGO_ENABLE_BASIC_AUTH` | Active l'auth basic DRF. | `False` |
| `GAME_API_WRITE_TOKEN` | Clé de bootstrap pour créer une session client. | Vide |
| `GAME_API_ACCESS_TOKEN_LIFETIME_SECONDS` | Durée de vie access token. | `900` |
| `GAME_API_REFRESH_TOKEN_LIFETIME_SECONDS` | Durée de vie refresh token. | `2592000` |
| `DJANGO_SECURE_SSL_REDIRECT` | Redirection HTTPS. | `True` |
| `DJANGO_SECURE_HSTS_SECONDS` | Durée HSTS. | `31536000` |

Le projet charge automatiquement `.env` au démarrage si ce fichier existe.

## Commandes utiles

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic
python manage.py test gameapi
```

## Documentation locale

Installer MkDocs :

```bash
pip install -r requirements-docs.txt
```

Lancer le site :

```bash
mkdocs serve
```

Construire le site statique :

```bash
mkdocs build
```

Le site généré est écrit dans `site/`.
