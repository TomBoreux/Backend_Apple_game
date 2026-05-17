# Backend Game

Backend Django/DRF pour l'API du jeu, la gestion des joueurs, des médecins,
des niveaux de référence et des rapports complets envoyés par le client.

La documentation projet est disponible sous forme de mini site MkDocs dans le
dossier `docs/`.

## Démarrage rapide

Depuis ce dossier :

```bash
python -m venv ../venv
source ../venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

En local, prévoir un fichier `.env` avec au minimum :

```env
DJANGO_SECRET_KEY=change-me-with-a-long-secret-key
POSTGRES_DB=godotgame
POSTGRES_USER=godotuser
POSTGRES_PASSWORD=change-me
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
GAME_API_WRITE_TOKEN=change-me-client-bootstrap-token
```

## Documentation

Installer l'outillage de documentation :

```bash
pip install -r requirements-docs.txt
```

Lancer le site localement :

```bash
mkdocs serve
```

Construire le site statique :

```bash
mkdocs build
```

Pages principales :

- `docs/index.md` : vue d'ensemble.
- `docs/installation.md` : installation, configuration et commandes Django.
- `docs/api.md` : endpoints et authentification.
- `docs/reports.md` : format `.dat`, génération de graphiques et statistiques.
- `docs/deployment.md` : points d'attention pour la production.

## Tests

```bash
python manage.py test gameapi
```

Les tests actuels couvrent surtout le parsing de rapports `.dat`, la
déduplication des blocs de rapports, les critères d'inclusion Android et les
séries statistiques.
