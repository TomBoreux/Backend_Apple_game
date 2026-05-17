# Integration avec la documentation frontend

La documentation frontend doit rester le site MkDocs final. La documentation
backend fournit seulement :

- des pages Markdown dans `docs/` ;
- un fragment de navigation dans `docs/backend-nav.yml` ;
- un script de synchronisation dans `scripts/sync_backend_docs.py`.

## Principe

Le frontend garde son `mkdocs.yml`. Pour integrer la section backend, ajouter
une seule fois ces marqueurs sous la cle `nav:` du `mkdocs.yml` frontend :

```yaml
nav:
  - Accueil: index.md
  # BEGIN BACKEND DOCS
  # END BACKEND DOCS
```

Le script backend remplacera uniquement le contenu entre ces deux marqueurs.
Toutes les modifications frontend situees ailleurs dans `mkdocs.yml` seront
conservees.

## Synchronisation manuelle

Depuis le repo backend :

```bash
python scripts/sync_backend_docs.py /chemin/vers/apple-game
```

Puis, dans le repo frontend :

```bash
mkdocs build --strict
```

## Synchronisation automatique recommandee

Dans le repo frontend, creer un workflow GitHub Actions qui :

1. checkout le repo frontend ;
2. checkout le repo backend dans un sous-dossier ;
3. lance `backend/scripts/sync_backend_docs.py .` ;
4. build MkDocs ;
5. ouvre une pull request si les fichiers generes changent.

Cette approche garde deux sources propres :

- le frontend controle le site final et sa navigation globale ;
- le backend controle sa section documentaire et son fragment de navigation.

## Pourquoi des marqueurs ?

MkDocs ne fusionne pas nativement plusieurs fichiers `mkdocs.yml`. Les marqueurs
evitent les conflits : le script ne touche qu'une zone reservee au backend.
