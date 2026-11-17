# Correspondance des chemins pour BRIEF-4 (sur ce PC)
BRIEF-4.md est copié tel quel (avec addendum, SHA-256 b52af6db…a38c1). Ses chemins /workspace/... désignent l'ordinateur de l'équipe ; dans ce repo ils sont ici :
- /workspace/review/CAHIER-PASSE-4-MATHS.md -> docs/CAHIER-PASSE-4-MATHS.md (v2.1.1, SHA-256 94e7e54b…e269f5)
- /workspace/data-ia/COORDINATION.md -> docs/COORDINATION.md (instantané du 18 nov. 2026)
- waves/*.yaml, waves/*.sha256, waves/vague1_errata.md -> waves/ (à la racine du repo)
- /workspace/review/revue-passe3.md -> docs/revue-passe3.md (revue NO-GO d'Évaluation)
- persist_v3 (base de persistance v3 de référence) -> scripts/persist_v3.py
Les fichiers de waves/ sont figés : ne jamais les modifier ; le code les vérifie contre waves/*.sha256.

## Périmètre de cette exécution (décision du 18 nov. 2026)
Ne réaliser QUE la Priorité 0 du BRIEF-4, addendum compris, dans cet ordre : B4 (freeze par question), B3 (hash complet chaîné, tête exportée, git_commit jamais « unknown »), B5 (stub toujours SYNTHETIC, published_at manquant refusé), puis A (import des vagues avec hash), C, E, puis B1 et B2, puis D si nécessaire ; plus la désactivation de la route GASTAT gastatapi en REAL et l'erreur pydantic sans valeurs d'environnement. Les items maths P1 et suivants (§10 du cahier) sont reportés après le 24 nov. : ne pas les commencer.
