# Automatisation frontend

Cette page precise l'integration automatique de la documentation backend dans
le site MkDocs frontend.

## Depot frontend

| Element | Valeur |
| --- | --- |
| Repo web | `https://github.com/matdu300/apple-game` |
| Remote git | `https://github.com/matdu300/apple-game.git` |
| Configuration MkDocs | `mkdocs.yml` a la racine du depot |
| Dossier de documentation | `docs/` |

Le repo GitHub est `matdu300/apple-game`. Le suffixe `.git` est reserve au
remote de clone, pas aux URL web ou raw.

## Marqueurs dans le mkdocs.yml frontend

Le `mkdocs.yml` frontend contient deja une section `nav:`. Ajouter une seule
fois le bloc reserve au backend sous `nav:`, par exemple a la fin :

```yaml
  - Developpement:
      - API Backend: API.md
      - Deploiement: deployment/index.md

  # BEGIN BACKEND DOCS
  # END BACKEND DOCS
```

Le script backend remplacera uniquement le contenu entre `BEGIN BACKEND DOCS`
et `END BACKEND DOCS`.

## Commande locale

Depuis le repo backend :

```bash
python scripts/sync_backend_docs.py /chemin/vers/apple-game
```

Sur la machine Windows de developpement :

```bash
python scripts/sync_backend_docs.py "C:\Users\marti\apple-game"
```

Le script copie les pages backend dans `apple-game/docs/backend/` puis met a
jour le bloc reserve du `mkdocs.yml` frontend.

## Workflow automatique propose

Dans le repo frontend, creer `.github/workflows/sync-backend-docs.yml` :

```yaml
name: Sync backend docs

on:
  workflow_dispatch:
  schedule:
    - cron: "0 6 * * 1"

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout frontend
        uses: actions/checkout@v4

      - name: Checkout backend
        uses: actions/checkout@v4
        with:
          repository: matdu300/backend_game
          path: backend_game

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install MkDocs
        run: python -m pip install -r backend_game/requirements-docs.txt

      - name: Sync backend docs
        run: python backend_game/scripts/sync_backend_docs.py .

      - name: Build documentation
        run: mkdocs build --strict

      - name: Create pull request
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "docs: sync backend documentation"
          title: "docs: sync backend documentation"
          body: "Synchronisation automatique de la documentation backend dans le site MkDocs frontend."
          branch: docs/sync-backend
```

Adapter `repository: matdu300/backend_game` au nom exact du repo backend si le
depot GitHub backend porte un autre nom.

## Strategie de maintenance

- Le frontend reste proprietaire du site final et du `mkdocs.yml` global.
- Le backend reste proprietaire de ses pages Markdown et de
  `docs/backend-nav.yml`.
- La synchronisation automatique ne modifie que `docs/backend/` et le bloc
  balise du `mkdocs.yml` frontend.
- Les changements frontend hors du bloc balise sont preserves.
