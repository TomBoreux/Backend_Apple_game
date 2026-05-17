# API

Toutes les routes API sont préfixées par `/api/`.

## Authentification

Le client du jeu n'utilise pas directement un compte Django. Il crée une
session API avec une clé de bootstrap, puis utilise un access token court durée.

### Créer une session client

`POST /api/auth/token/`

Authentification requise : clé `GAME_API_WRITE_TOKEN`, envoyée par l'un des
moyens suivants :

- en-tête `X-Game-Api-Key` ;
- champ `api_key` dans le corps de requête ;
- paramètre `?api_key=`.

Exemple :

```bash
curl -X POST http://localhost:8000/api/auth/token/ \
  -H "X-Game-Api-Key: $GAME_API_WRITE_TOKEN" \
  -F "uuid=device-123"
```

Réponse `201` :

```json
{
  "access_token": "...",
  "access_token_expires_at": "2026-05-17T12:15:00+00:00",
  "expires_in": 900,
  "refresh_token": "...",
  "refresh_token_expires_at": "2026-06-16T12:00:00+00:00",
  "token_type": "Bearer",
  "session_id": 1
}
```

### Rafraîchir une session

`POST /api/auth/refresh/`

Le refresh token peut être envoyé dans le champ `refresh_token`, dans
l'en-tête `X-Refresh-Token` ou dans le paramètre `?refresh_token=`.

Les refresh tokens sont rotatifs : chaque appel remplace le refresh token
précédent.

```bash
curl -X POST http://localhost:8000/api/auth/refresh/ \
  -F "refresh_token=$REFRESH_TOKEN"
```

## Autorisations

| Action | Autorisation |
| --- | --- |
| Créer une session API | `GAME_API_WRITE_TOKEN` |
| Créer ou mettre à jour un joueur | Bearer token ou compte staff |
| Créer un seed | Bearer token ou compte staff |
| Envoyer un rapport | Bearer token ou compte staff |
| Lister tous les utilisateurs, médecins, seeds ou rapports | Compte staff |
| Supprimer une ressource | Compte staff |
| Consulter graphiques et statistiques | Compte staff |

Un compte staff Django authentifié via l'admin peut effectuer les actions
protégées côté administration.

## Joueurs

### Récupérer un joueur

`GET /api/user/<id>/`

Requiert un Bearer token ou un compte staff.

### Récupérer un joueur par token

`GET /api/user/?token=<player-token>`

Le client du jeu doit utiliser ce filtre. Sans filtre, la liste complète est
réservée au staff.

### Créer ou mettre à jour un joueur

`POST /api/user/`

Champs :

| Champ | Obligatoire | Description |
| --- | --- | --- |
| `token` | Oui | Identifiant joueur côté client. |
| `uuid` | Oui sauf `token=guest` | UUID appareil ou joueur. |
| `birth_year` | Non | Année de naissance. |
| `doctor_token` | Non | Token d'un médecin existant à associer. |

Comportement :

- `token=guest` utilise un joueur invité partagé.
- pour les autres joueurs, `uuid` est obligatoire ;
- si un joueur avec le même `token` existe, il est mis à jour ;
- `doctor_token` doit correspondre à un médecin existant.

Exemple :

```bash
curl -X POST http://localhost:8000/api/user/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "token=player-001" \
  -F "uuid=device-123" \
  -F "birth_year=2012"
```

Réponse :

```json
{
  "id": 1,
  "token": "player-001",
  "uuid": "device-123",
  "birth_year": 2012,
  "doctors": [],
  "latest_doctor_id": null,
  "latest_doctor_token": "",
  "doctor_key": ""
}
```

### Supprimer un joueur

`DELETE /api/user/<id>/`

Réservé au staff.

## Médecins

### Lister ou lire

- `GET /api/doctor/` : liste complète, staff uniquement.
- `GET /api/doctor/<id>/` : détail.
- `GET /api/doctor/?token=<doctor-token>` : recherche par token.

### Créer

`POST /api/doctor/`

Réservé au staff.

Champs obligatoires :

| Champ | Description |
| --- | --- |
| `last_name` | Nom. |
| `first_name` | Prénom. |
| `token` | Token unique utilisé par le client. |
| `email` | Email unique. |

### Supprimer

`DELETE /api/doctor/<id>/`

Réservé au staff.

## Niveaux de référence

### Lister ou lire

- `GET /api/seed/` : liste, staff uniquement.
- `GET /api/seed/<id>/` : détail, staff uniquement.

### Créer ou retrouver

`POST /api/seed/`

Requiert un Bearer token ou un compte staff.

Champs :

| Champ | Obligatoire | Description |
| --- | --- | --- |
| `name` | Oui | Nom fonctionnel du seed. |
| `file` | Oui si nouveau seed | Fichier de niveau. |

Si un seed avec le même `name` existe déjà, l'API retourne l'objet existant au
lieu d'en créer un nouveau.

## Rapports complets

Les routes historiques `/api/full-report/...` sont aussi disponibles, mais les
routes canoniques documentées ici utilisent `/api/fullreport/...`.

### Lister ou lire

- `GET /api/fullreport/` : liste complète, staff uniquement.
- `GET /api/fullreport/<id>/` : détail, staff uniquement.

### Envoyer un rapport

`POST /api/fullreport/`

Requiert un Bearer token ou un compte staff.

Champs :

| Champ | Obligatoire | Description |
| --- | --- | --- |
| `user` | Oui | ID du joueur. |
| `session_id` | Oui | Identifiant de session de jeu. |
| `file` | Oui | Fichier `.dat` ligne par ligne. |
| `seed_levels` | Non | IDs de seeds, répétés ou séparés par virgule. |
| `seeds` | Non | Alias de `seed_levels`. |
| `seed` | Non | Alias de `seed_levels`. |
| `app_version` | Non | Version applicative lisible. |
| `app_version_code` | Non | Version numérique entière. |
| `level_generation_version` | Non | Version du générateur de niveaux. |
| `client_platform` | Non | Plateforme client, par exemple `android`. |

Exemple :

```bash
curl -X POST http://localhost:8000/api/fullreport/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "user=1" \
  -F "session_id=session-abc" \
  -F "client_platform=android" \
  -F "app_version=1.0.0" \
  -F "app_version_code=100" \
  -F "level_generation_version=v3" \
  -F "seed_levels=1,2,3" \
  -F "file=@report.dat"
```

Comportement d'append :

- l'unicité métier est `(user, session_id)` ;
- si le rapport existe déjà, seuls les nouveaux blocs `.dat` sont ajoutés ;
- les blocs déjà présents ou dupliqués dans l'upload sont ignorés ;
- l'en-tête du fichier uploadé doit annoncer le nombre total de niveaux après
  fusion ;
- si l'en-tête existant est trop court pour être réécrit, l'API renvoie une
  erreur.

### Supprimer un rapport

`DELETE /api/fullreport/<id>/`

Réservé au staff.

## Graphiques et statistiques

### Graphique PNG d'un rapport

`GET /api/fullreport/<id>/chart/`

Réservé au staff. Retourne `image/png`.

### Statistiques d'un rapport

`GET /api/fullreport/<id>/stats/`

Réservé au staff.

- JSON par défaut.
- HTML si `Accept: text/html`.
- JSON forcé avec `?format=json`.

Un rapport individuel est exclu des statistiques d'étude si :

- `client_platform` n'est pas `android` ;
- il contient moins de 3 niveaux.

### Statistiques globales

`GET /api/fullreport/stats/`

Réservé au staff.

La réponse inclut :

- le nombre total de rapports ;
- le nombre de rapports Android ;
- les rapports analysés ;
- les rapports exclus ;
- les rapports en erreur ;
- les agrégats globaux ;
- les séries utilisées pour les graphiques HTML.

## Codes d'erreur fréquents

| Code | Cas courant |
| --- | --- |
| `400` | Champ obligatoire absent, fichier `.dat` invalide, entier invalide. |
| `401` | Token absent, invalide ou expiré. |
| `403` | Action réservée au staff ou liste demandée sans filtre. |
| `404` | Ressource introuvable ou fichier de rapport absent. |
| `503` | API non prête sans `GAME_API_WRITE_TOKEN`, ou dépendances chart absentes. |
