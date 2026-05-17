# Rapports et statistiques

Les rapports complets sont stockés dans le modèle `FullReport` et dans des
fichiers `.dat` sous `MEDIA_ROOT/reports/full/`.

## Modèle de données

Un rapport contient :

| Champ | Description |
| --- | --- |
| `session_id` | Identifiant de session de jeu. |
| `user` | Joueur propriétaire du rapport. |
| `file` | Fichier `.dat` fusionné. |
| `date` | Date de création. |
| `app_version` | Version applicative lisible. |
| `app_version_code` | Version applicative numérique. |
| `level_generation_version` | Version du générateur de niveaux. |
| `client_platform` | Plateforme client. |
| `seed_levels` | Niveaux de référence associés. |

L'unicité applicative est `(user, session_id)`.

## Format `.dat`

Le fichier commence par le nombre de niveaux, puis enchaîne un bloc par niveau.

Structure d'un bloc :

| Ligne | Type | Description |
| --- | --- | --- |
| 1 | entier | Seed du niveau. |
| 2 | nombre | Temps passé sur le niveau. |
| 3 | `int int` | Coordonnées du panier. |
| 4 | `int int` | Coordonnées du pommier. |
| 5 | `int int int` | Marqueur visuel. Si le premier entier vaut `1`, les deux suivants sont utilisés. |
| 6 | entier | Nombre d'arbres. |
| 7..n | `int int` | Coordonnées de chaque arbre. |
| n+1 | entier | Nombre de positions joueur. |
| suite | `float float` | Positions successives du joueur. |
| fin optionnelle | nombre | Distance finale. |
| fin optionnelle | entier | Score en étoiles. |

Exemple minimal :

```text
01
42
12.5
0 0
5 5
1 2 3
0
2
0.0 0.0
1.0 1.0
1.5
3
```

Dans cet exemple :

- le fichier annonce 1 niveau ;
- le niveau a le seed `42` ;
- le joueur a joué `12.5` unités de temps ;
- il n'y a pas d'arbre ;
- deux positions joueur sont enregistrées ;
- la distance finale vaut `1.5` ;
- le score vaut `3`.

## Upload progressif

Le client peut envoyer un même rapport en plusieurs fois.

Quand `POST /api/fullreport/` reçoit un fichier pour un couple `(user,
session_id)` déjà connu :

1. le fichier existant est relu ;
2. les blocs déjà présents sont identifiés ;
3. les blocs nouveaux sont ajoutés ;
4. les doublons sont ignorés ;
5. l'en-tête du fichier existant est mis à jour avec le nombre total de niveaux.

L'en-tête de l'upload doit indiquer le nombre total attendu après fusion, pas
seulement le nombre de blocs présents dans cet upload.

Exemple :

- le serveur possède déjà 2 niveaux ;
- le client envoie 1 nouveau niveau ;
- l'en-tête de l'upload doit annoncer `3`.

## Calculs par niveau

Pour chaque niveau, le backend calcule notamment :

| Champ | Calcul |
| --- | --- |
| `traveled_distance` | Somme des distances entre positions successives du joueur. |
| `target_distance` | Distance entre le panier et le pommier. |
| `malus_time` | `6 + 2 * nombre_arbres`. |
| `playable_time` | `max(time_spent - malus_time, 0)`. |
| `expected_distance` | `playable_time * 2`. |
| `speed` | `traveled_distance / playable_time`, ou `0`. |
| `movement_ratio` | `traveled_distance / expected_distance`, ou `0`. |
| `movement_percent` | `movement_ratio * 100`. |
| `movement_percent_per_star` | `movement_percent / score`, si le score est positif. |
| `is_interrupted` | Vrai si `final_distance` ou `score` est absent. |

## Statistiques d'un rapport

`GET /api/fullreport/<id>/stats/`

Le backend retourne les métriques globales du rapport, les niveaux enrichis et
les séries graphiques.

Un rapport peut être marqué `excluded: true` si :

- sa plateforme n'est pas `android` ;
- il contient moins de 3 niveaux.

Ces critères correspondent aux constantes applicatives :

| Constante | Valeur |
| --- | --- |
| `STUDY_CLIENT_PLATFORM` | `android` |
| `MIN_STUDY_LEVEL_COUNT` | `3` |

## Statistiques globales

`GET /api/fullreport/stats/`

Les statistiques globales ne mélangent pas tous les rapports indistinctement.
Le backend :

1. ignore les rapports sans fichier ;
2. exclut les rapports non Android ;
3. exclut les rapports avec moins de 3 niveaux ;
4. signale les fichiers illisibles ou invalides ;
5. agrège uniquement les rapports analysables.

Les agrégats incluent :

- nombres de niveaux terminés ou interrompus ;
- temps total et moyen ;
- distance parcourue totale et moyenne ;
- score moyen ;
- pourcentage moyen de mouvement ;
- mouvement moyen par étoile ;
- vitesse moyenne ;
- regroupement par seed ;
- séries graphiques par âge et par vitesse.

## Sortie HTML

Les endpoints de statistiques peuvent rendre un dashboard HTML :

```bash
curl http://localhost:8000/api/fullreport/stats/ \
  -H "Accept: text/html"
```

Pour forcer le JSON :

```bash
curl http://localhost:8000/api/fullreport/stats/?format=json
```

## Graphique PNG

`GET /api/fullreport/<id>/chart/`

Ce endpoint génère une image PNG avec `matplotlib` et `numpy`.

Le graphique montre :

- panier ;
- pommier ;
- repère visuel si présent ;
- arbres ;
- position de départ du joueur ;
- trajectoire du joueur ;
- seuils angulaires à 20 et 40 degrés.

Si `matplotlib` ou `numpy` manque, l'API renvoie `503`.
