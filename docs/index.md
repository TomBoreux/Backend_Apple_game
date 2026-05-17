# Backend Game

Cette documentation décrit le backend Django/DRF du jeu : son installation,
ses endpoints API, le format des rapports envoyés par le client et les points
d'attention pour l'exploitation.

## Rôle du projet

Le backend fournit :

- une API d'authentification courte durée pour le client du jeu ;
- la création et la mise à jour des joueurs ;
- l'association optionnelle d'un joueur à un médecin ;
- l'enregistrement de niveaux de référence (`SeedLevel`) ;
- l'upload progressif de rapports complets au format `.dat` ;
- des vues d'administration pour consulter, télécharger et analyser les
  rapports ;
- des sorties statistiques en JSON ou HTML.

## Structure utile

| Chemin | Rôle |
| --- | --- |
| `config/settings.py` | Configuration Django, base PostgreSQL, sécurité, DRF, tokens API. |
| `config/urls.py` | Routes globales, pages HTML publiques, admin et préfixe `/api/`. |
| `gameapi/models.py` | Modèles `Doctor`, `User`, `SeedLevel`, `FullReport`, `GameApiTokenSession`. |
| `gameapi/views.py` | Endpoints API, authentification, parsing des uploads, dashboards HTML. |
| `gameapi/report_charts.py` | Parsing des rapports, calculs statistiques et génération PNG. |
| `gameapi/admin.py` | Interface admin, téléchargement `.dat`, liens graphiques et stats. |
| `gameapi/tests.py` | Tests unitaires existants sur les rapports et les statistiques. |

## Parcours typique

1. Un client obtient une session via `POST /api/auth/token/` avec la clé de
   bootstrap `GAME_API_WRITE_TOKEN`.
2. Le client utilise l'access token `Bearer` pour créer ou mettre à jour un
   joueur via `POST /api/user/`.
3. Le client peut créer ou retrouver un niveau de référence via `POST /api/seed/`.
4. Le client envoie un rapport complet via `POST /api/fullreport/`.
5. Un administrateur consulte les rapports dans `/admin/` ou via les endpoints
   de stats et graphiques.

## Conventions importantes

- Les réponses API sont rendues en JSON par défaut.
- Les endpoints de statistiques peuvent rendre du HTML si l'en-tête `Accept`
  contient `text/html`; ajouter `?format=json` force le JSON.
- Les rapports utilisés dans les statistiques d'étude doivent venir de la
  plateforme `android`.
- Les statistiques d'étude excluent les rapports contenant moins de 3 niveaux.
- Les suppressions et la consultation complète des données sont réservées aux
  comptes staff Django.
