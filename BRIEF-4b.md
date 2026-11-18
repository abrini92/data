# BRIEF-4b — Migration du registre de production (18 nov. 2026)

Repo : C:\Users\Abderrahim\data, branche main. Commits locaux uniquement, AUCUN push. Ne jamais modifier waves/. Pas de gel de production de P1 dans cette passe.

## Problème
Après la passe 4, `data-ia verify-registry` sur la base de production `data/dataia.db` échoue :
`sqlite3.OperationalError: no such column: forecast_registry.prev_sha256`.
Le schéma (prev_sha256, p_base, baseline_method, series_id, vintage_sha256, observations_content_hash, seed_hash, wave_id, etc.) a changé sans migration.

## À faire
1. Commande `data-ia migrate-registry [--db PATH] [--dry-run]` :
   - Avant toute écriture : sauvegarde horodatée de la base (copie fichier, ex. data/backups/dataia-YYYYMMDD-HHMMSS.db), chemin affiché. Une sauvegarde manuelle existe déjà : data/backups/dataia-pre-4b.db (ne pas y toucher).
   - `--dry-run` : affiche les colonnes à ajouter, le nombre de lignes legacy, la genèse prévue ; n'écrit rien.
   - Migration EN AJOUT SEUL : ALTER TABLE ADD COLUMN pour les colonnes manquantes ; aucune suppression, aucune réécriture des valeurs existantes (probability, sha256, etc. inchangés). Idempotente (relancer ne change rien).
   - Les lignes existantes sont marquées legacy (pré-chaîne) : leur sha256 d'origine reste vérifiable selon l'ancien schéma de hash.
   - Une ligne/enregistrement de genèse de chaîne est écrit après elles ; il inclut un hash de l'ensemble des lignes legacy, et la tête de chaîne exportée hors base (B3) démarre à cette genèse.
2. `verify-registry` : vérifie les lignes legacy avec l'ancien hash, puis la chaîne à partir de la genèse ; détecte toujours réécriture et suppression.
3. Exclusion d'une ligne du score, en ajout seul : la dernière ligne du registre de production (écrite le 18 nov. vers 02:53 heure de Riyad par un cycle de vérification de la passe 3b) doit être traitée comme TEST et exclue de `brier`, SANS être supprimée ni réécrite. Mécanisme : une table/enregistrement d'annotation en ajout seul (id de ligne, label TEST, raison, horodatage), pris en compte par `brier` et affiché par verify. Commande, ex. `data-ia annotate-forecast --id N --label TEST --reason "..."`. Appliquer cette annotation à cette ligne dans la base de production après la migration.
4. Tests :
   - test de migration sur une base à l'ancien schéma (fixture) : colonnes ajoutées, valeurs inchangées, idempotence, dry-run sans écriture, sauvegarde créée ;
   - test qui copie la vraie base data/dataia.db dans un dossier temporaire, migre la copie, et prouve que verify-registry passe (skip propre si le fichier est absent) ;
   - test que brier exclut une ligne annotée TEST ;
   - verify détecte encore une réécriture et une suppression après migration.
5. Exécuter ensuite sur la base de production : dry-run, puis migration, puis annotation, puis `verify-registry` (doit sortir 0). Coller les sorties dans le résumé.

## Compte rendu
Code de sortie, commits (hash et message), pytest, chemin de la sauvegarde, sortie du dry-run, sortie de verify-registry sur la production après migration, id de la ligne annotée TEST, ce qui reste ouvert.
