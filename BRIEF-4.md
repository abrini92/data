# BRIEF-4 — Passe 4 Data IA (orchestrateur, 18 nov. 2026)

Repo : C:\Users\Abderrahim\data, branche main, local. Commits locaux uniquement : AUCUN push sans l'accord explicite de l'utilisateur. Pas de secret dans le repo. Toute donnée synthétique est étiquetée SYNTHETIC. Pas de routes internes (SAMA, open.data, GASTAT /o/).
Prérequis : la passe 3b est terminée (bugs et tests de Modèle, item 12 du cahier). Ce qui reste ouvert de l'item 12 après la 3b passe dans cette passe.
Référence maths : /workspace/review/CAHIER-PASSE-4-MATHS.md v2.1, SHA-256 4c8b91b4758fd24cabb23beb06030b03b3e562065863db0be32a09ee650c3b87 (§10).
Référence décisions et calendrier : /workspace/data-ia/COORDINATION.md (prime sur tout autre document).

## Priorité 0 (ÉCHÉANCE DURE : opérationnel le 26 nov. ; sinon repli minimal)
A. Import des vagues : waves/vague1.yaml et waves/vague1b.yaml, avec vérification du SHA-256 contre waves/*.sha256 ; refus net si le hash diffère. Lecture de vague1_errata.md (résolutions P7, P8, P13 ; P16 conditionnelle) et de vague1_bases.yaml (hash consigné).
B. Gel par question : prévision figée en ajout seul dans le registre, avec forecast_at, data_cutoff, hash des données et de la config, et base naïve calculée au même data_cutoff (persist_v3 pour P1, P3, P5, P9, P11, P12, P14 ; fréquence sinon ; 0,5 seulement en dernier recours avec justification écrite). Refus de geler après l'échéance de gel de la question.
C. Calendrier de gel en config (heure de Riyad, UTC+3) : P17 dès que possible ; **P1 le 30 nov. à 23:59** ; P7 le 6 déc. à 09:00 ; P3 le 7 déc. à 09:00 ; P9 le 8 déc. à 09:00 ; P5 le 11 déc. à 23:59 au plus tard ; P11, P12, P14, P15 le 29 déc. à 09:00 ; P10 le 8 janv. à 23:59 ; P6 avant le 25 janv. ; P8, P13, P16 avant le 10 févr. (Le cahier indique le 8 déc. pour P5 : un gel plus tôt reste valide, mais la référence est COORDINATION.)
D. Repli minimal (déclenché le 26 nov. si A à C ne marchent pas) : persistance v3 ou fréquence, figée et hachée, en ajout seul, avec replay.
E. Rapprochement : `brier` relie les prévisions du registre aux questions résolues par id de vague et de question.

## Priorité 1 et suivantes (maths)
Les items 1 à 11 du §10 du cahier, dans l'ordre P0 > P1 > P2. Tests obligatoires : σ̂²_u ne contient pas σ²_η ; |P_t − P_MC| < 0,01 ; ν > 2 ; R PSD ; poids du bridge ≤ 1/3 ; θ* dérivé de `rounding`, jamais en dur ; aucune valeur PMI dans les rapports.

## Hors périmètre
Arbre complet de la question cible et questions de preuve de la vague 2 : passe 5.

## Compte rendu attendu (à l'orchestrateur)
Code de sortie, commits (hash et message), pytest, démonstration d'import avec hash valide et invalide, gel factice de P1 sur données réelles (étiqueté TEST, dans un registre de test séparé ; le registre de production n'est jamais modifié), replay, statut de chaque item du §10, et ce qui reste ouvert.

## ADDENDUM 18 nov. 02:58 — NO-GO Évaluation sur cf3a41c (/workspace/review/revue-passe3.md)
Les corrections B1 à B5 entrent dans la PRIORITÉ 0, avant A à E, avec les tests de bout en bout demandés par Évaluation :
- B1 : brier rejette toute prévision écrite après la résolution (ou après l'échéance de gel), garde une seule prévision par question (la dernière figée avant le gel) et prend l'étiquette de l'issue. Test : le scénario synthétique d'Évaluation doit donner n = 0, ou être rejeté.
- B2 : la base naïve n'utilise que les issues antérieures au data_cutoff, jamais celle de la question. La persistance v3 est dans le code, et p_base est stocké dans le registre.
- B3 : hashes chaînés (chaque ligne inclut le hash de la précédente), avec une tête de chaîne exportée hors de la base (fichier ajouté au fur et à mesure et commit git). Le hash couvre les observations, le seed, p_base, la série, le millésime et config_hash ; git_commit ne vaut jamais « unknown » (refus sinon). Test : verify détecte une réécriture cohérente et une suppression.
- B4 : commande freeze par question, avec un data_cutoff distinct de forecast_at, la série et le millésime, la base v3, et un refus après l'échéance. Test : fige P1 dans un registre de test.
- B5 : une extraction stub donne toujours SYNTHETIC, quel que soit le statut HTTP ; un published_at manquant est refusé, sans repli. Test : un collect live suivi d'un stub donne SYNTHETIC.
- Route GASTAT gastatapi/portal/api : désactivée en REAL tant que tu n'as pas prouvé que c'est une API publique documentée et que robots.txt l'autorise. On ne prend pas les cartes de la page d'accueil comme données.
- La sortie d'erreur pydantic ne doit afficher aucune valeur de variable d'environnement.
Échéances : revérification par Évaluation au plus tard le 28 nov. Si ce n'est pas fait, P1 est figée en MANUAL par Modèle (hachée, hors du score du moteur), et le moteur vise P7 le 6 déc.
Les points IMPORTANTS (replay avec config_hash, bootstrap par blocs, verdict sur l'IC, n_eff) passent en P1 de la passe 4.
