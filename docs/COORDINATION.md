# Data IA – fichier de coordination (source unique de vérité)
Tenu par l'orchestrateur (Grok Bot). Mis à jour : 18 nov. 2026, 02:20 (heure de Riyad, UTC+3).

## Règles pour toute l'équipe
1. Lire ce fichier avant toute action. En cas de conflit entre ce fichier et un autre document, ce fichier fait foi.
2. Toute question, tout désaccord ou toute décision passe par l'orchestrateur, jamais directement par l'utilisateur.
   Exception : les décisions réservées à l'utilisateur (push GitHub, dépenses, clés et secrets, changement de vision).
3. Seul Dev modifie le repo sur le PC. Aucun push sans OK explicite de l'utilisateur. Aucun secret dans le repo.
4. Pas de chiffres, d'endpoints ni de conditions inventés. Les données synthétiques sont toujours étiquetées SYNTHETIC.
5. Quand un bot change un fichier partagé, il le signale à l'orchestrateur, qui met ce fichier à jour.

## Décisions actées
- Question cible (utilisateur, 18 nov.) : "Will Saudi real non-oil activities grow by at least 4.5% in 2027, according to GASTAT's first estimate of 2027 annual real GDP?" Seuil calé sur la prévision du FMI (Article IV, juillet 2026). Page Produit : https://cursor.com/canvas/store-1c7b08f1-3f04-4de4-865c-426fcee496db/6ceaaf62-366a-4627-a492-8673079eee18
- Starlink abandonné comme question cible.
- Classes de sources (grille validée par l'utilisateur) : A 0,90 / B 0,80 / C 0,75 / D 0,50, ajustement ±0,10.
- CST : classe C, prior 0,85 (C + 0,10).
- open.data.gov.sa et SAMA : pas d'API exploitable ; ne pas utiliser de routes internes.
- Scraping interdit : Umm Al-Qura, KAPSARC, Ookla, Saudi Exchange, Etimad.
- Correspondance score→a priori (NIG) : PROVISIONAL, b0 = 0, κ0 = 2, ν0 = 4 (BRIEF-3b).
- Paquet Produit (18 nov.) : vague 1 de 17 questions de preuve (15 actives, P16 et P17 sous condition) ; objectif d'au moins 30 questions effectives (n_eff) résolues avant de conclure ; P6 ancrée sur l'OPEC MOMR (moyenne T3 2025, sources secondaires) ; P17 = dépenses FY2027 de la déclaration pré-budgétaire du MoF (>), figée avant le budget ; arbre de 8 moteurs ILLUSTRATIVE, poids en config ; M3, M4 et M5 corrélés.
- Persistance probabiliste V3 (en vigueur) pour P1, P3, P5, P9, P11, P12, P14 : /workspace/review/base-persistance-probabiliste.md + persist_v3.py. Deux états (hausse stricte / non-hausse, zéro = non-hausse) ; f = (h+1)/(m+2) ; p_haut = (u_d+4f)/(n_d+4) si ≥ 6 transitions, sinon f ; < 3 variations → 0,5 justifié ; bornes [0,05 ; 0,95] ; K ≤ 12 ; série unique hashée ; recalcul à chaque forecast_at. Les v1/v2 sont caduques.
- Base naïve : jamais 0,5 par défaut. Sans historique, utiliser la persistance (statu quo) ; 0,5 seulement si aucune base défendable n'existe, avec justification écrite.

## Périmètre des passes
- Passe 3 (lancée à 02:13) + 3b (/workspace/brief3/BRIEF-3b.md, bugs et tests de Modèle) : BRIEF-3 (/workspace/brief3/BRIEF-3.md) + la question cible ci-dessus (arbre vide, statut "not ready") + la correspondance des a priori + les BUGS et TESTS de la liste de Modèle (dont le cycle par défaut cassé).
- Passe 4 : les 8 résultats maths de Modèle (cible continue, Student-t et P(Y>θ), choc commun, etc.), l'arbre de Produit, les questions de preuve, les idées de Recherche.

## Fichiers de référence
- Brief passe 3 : /workspace/brief3/BRIEF-3.md
- Registre des sources : /workspace/brief3/sources_verified.yaml (CST à corriger en C)
- Liste maths : /workspace/review/passe3-liste-maths-VALIDEE.md
- Note d'état de l'art : /workspace/out/note_etat_de_l_art_modele.md
- Repo : C:\Users\Abderrahim\data (main, local, non poussé)

## Qui fait quoi maintenant
- Dev : lance la passe 3, puis renvoie EXIT, commits, tests, GASTAT et résultats de preuve.
- Modèle : prépare le cahier de la passe 4 (cible continue).
- Produit : paquet final livré ; corrige la base naïve à 0,5.
- Sources : séries GASTAT et FMI ; relever le seuil de P6 (OPEC MOMR) et celui de P17 (MoF) ; date de publication tourisme T3 2026 ; calendrier GASTAT et SAMA de décembre à février.
- Recherche : soutien de Modèle pour la passe 4.
- Évaluation : relit les résultats de la passe 3 dès qu'ils arrivent.

## Décisions du 18 nov., 02:25 (verdict d'Évaluation sur la base v2)
- Une seule série par question, fixée avant t0, la même pour la base et la résolution ; millésime à t0 archivé (capture + hash) ; résolution sur le point précédent révisé dans la même publication (recommandé, à figer par Produit).
- Variations nulles = non-hausses ; base recalculée à chaque forecast_at avec le même data_cutoff.
- Bornes [0,05 ; 0,95] ; p_haut = (u_d + 4f)/(n_d + 4), f = (h+1)/(m+2) ; f en base de contrôle (battre Markov sans battre f = pas de conclusion).
- 30 questions effectives = point d'étape ; conclusion formelle ≥ 50 (cible 100) ; taille d'effet minimale détectable toujours rapportée.
- Liste des questions + séries figées et hachées avant la première prévision.
- Vague 1 = 15 questions (P16 sous condition), figée et hachée par Produit dans waves/vague1.yaml + vague1.sha256. P6 et P17 → vague 1b, hachée après le relevé de Sources.
- Échéance critique : P1 se tranche le 7 déc. 2026 → la prévision figée doit exister au plus tard le 5 déc., 23:59, heure de Riyad. Le moteur doit savoir figer des prévisions avant cette date (passe 3).
- Durée du pilote : plusieurs mois (≥ 50 questions effectives). Deck go / no-go à mettre à jour après le calcul de n_eff de la vague 1 par Modèle.
- Base de persistance v3 validée : /workspace/review/base-persistance-probabiliste.md + persist_v3.py (référence d'implémentation pour Dev en passe 4). La valeur précédente est celle imprimée dans la publication qui tranche (P2, P4).

- Base de la question cible (18 nov., 02:30) : base formelle préenregistrée = fréquence historique 2018-2025 de « ≥ 4,5 % » (persistance en contrôle). « FMI au seuil » (≈ 0,5) = référence d'expert affichée en tête du rapport (« battre le FMI »), pas la base formelle. Une seule question cible ne prouve rien statistiquement : la preuve repose sur les questions de preuve.
- Note Recherche pour la passe 4 : σ²_η compté deux fois (NIG sur les erreurs nettes de η̂_t), R PSD, Monte Carlo comme référence, bridge dans un groupe γ avec FMI et Banque mondiale. Modèle intègre.
- Vague 1 FIGÉE : waves/vague1.yaml, SHA-256 36d214bb…2311, gel 2026-11-18T02:22:55+03:00 (15 questions, P16 conditionnelle). Ne jamais modifier : toute correction = annulation + nouvelle vague. Modèle calcule les bases naïves, n_eff et rho, à figer avant le 5 déc. 23:59 ; Sources + Modèle vérifient la méthode de P11 et P14 sur le dernier point ; Dev importe la vague dans le registre (passe 4).
- Question cible, précisions (18 nov., 02:35) : « première estimation » = flash T4 2027 de GASTAT (publication attendue vers le 31 janv. ou le 1er févr. 2028, [à confirmer]). Seuil de 4,5 inchangé (choix de l'utilisateur). Écart de définition documenté : le seuil vient du « non-oil GDP » FMI, la résolution porte sur les « non-oil activities » GASTAT (2025 : FMI 4,2 % / GASTAT 4,9 %). Le benchmark « FMI au seuil » est donc approximatif ; références affichées : Article IV (4,5 % en 2027) et REO/MCDREO (4,05 % en 2027, édition [à confirmer]).
- Séries de croissance non pétrolière : /workspace/data-ia/series_croissance_non_petroliere.yaml (Sources, 9 séries) + raw/.
- Calendrier GASTAT : /o/ interdit par robots.txt → lecture manuelle dans un navigateur (orchestrateur).

## Décisions du 18 nov., 02:40 (n_eff de la vague 1, /workspace/review/neff_vague1.md)
- n_eff de la vague 1 = 4,48 (4,40 avec P11–P12 à ρ = 1), avec des ρ par CONVENTION. Plafond d'environ 11 si le facteur macro est commun à toutes les vagues → avec des questions 100 % macro saoudiennes, le seuil de 50 est hors d'atteinte. CONSÉQUENCE : à partir de la vague 2, les vagues doivent être conçues pour maximiser n_eff (domaines diversifiés, faible facteur commun, cadence plus rapide).
- Base principale = persistance v3 pour P1, P3, P5, P9, P11, P12, P14 ; fréquence historique en contrôle. Fréquence historique principale pour les autres questions.
- P11–P12 groupées à ρ = 1 (même bulletin SAMA, convention prudente).
- G_GDP : P7 vient des comptes détaillés du T3, P8 et P13 du flash T4. La vague 1 n'est pas modifiée ; les erreurs de métadonnées vont dans waves/vague1_errata.md (hors hash). Le moteur de P7 est à corriger dans l'errata.
- σ_d sera estimé sur la vague 1 et préenregistré avant la vague 2 ; wild cluster bootstrap.
- Durée du pilote et deck go / no-go : en attente de la conception de la vague 2.
- Vague 2 : proposition de Produit dans waves/vague2_regles_PROPOSITION.md (environ 20 questions, n_eff ≥ 8 par vague, gel toutes les 2 semaines, domaines diversifiés). En attente du chiffrage de Modèle (vague2_neff_Modele.md) et des séries de Sources (vague2_series_candidates.yaml). ClickUp : z8q7hbw9h6 (Produit), z8q7hbw9h7 (Sources).
- Vague 1b FIGÉE : waves/vague1b.yaml, SHA-256 95c1f375…77f0 (P6 ≥ 9,705 Mb/j au MOMR de janv. 2027, échéance 25 janv. ; P17 dépenses du budget FY2027 > 1 392 Md SAR, échéance 31 déc.). URGENT : base de P17 à figer avant l'annonce du budget (début déc., [à confirmer]) ; si le moteur ne fige pas à temps, P17 est hors preuve du moteur (une prévision MANUAL de Modèle est possible, étiquetée et exclue du score). P16 : risque d'annulation (série tourism.sa non vérifiée).
- Calendrier GASTAT relevé : calendrier_gastat_2026-11-18.md (PIB T3 le 8 déc., BCI le 9 déc., IPI d'oct. le 10 déc., IPC le 15 déc., marché du travail le 31 déc. ; flash T4 2026 et IPI de nov. non listés).
- Calendrier des gels : P17 dès maintenant ; P1 le 5 déc. à 23:59 ; P7 le 6 déc. à 09:00 ; P3 le 7 déc. à 09:00 ; P9 et P5 le 8 déc. à 09:00 ; P11, P12, P14, P15 le 29 déc. à 09:00 ; P2, P4, P10 en janv. ; P6 avant le 25 janv. ; P8, P13, P16 avant le 10 févr. Dates manquantes : budget FY2027, MOMR de déc. (Sources).
- Vague 2 (18 nov., 02:45) : objectif par vague = n_eff ≥ 7 ET charge macro moyenne ≤ 0,13, vérifiés avant le gel ; règles (a) à (f) de Modèle adoptées ; commande d'au moins 10 candidates à lien faible (Produit + Sources), vague 2 prête avant le 2 déc. Durée estimée par Modèle : environ 5 mois jusqu'à 30, 6 à 9 mois jusqu'à 50 (une vague toutes les 2 semaines). Règle d'arrêt : borne supérieure de la corrélation entre vagues > 0,05 après 4 vagues → décision de l'orchestrateur. vague1_bases.yaml : hash ed3b0714…df02d, n_eff = 4,40.
- Cahier maths passe 4 v2 (6771b56a…883b), décisions §9 (18 nov.) : arrondi au plus proche, θ* = 4,45 (provisoire, Sources vérifie le format GASTAT) ; base naïve de la cible sur les premières publications, 2020 incluse, variante sans 2020 en sensibilité ; millésimes FMI et BM demandés à Sources ; écart de définition FMI/GASTAT affiché (biais b_s) ; poids du bridge plafonné à 1/3 dans le groupe γ jusqu'à l'estimation de la covariance ; la persistance de référence est la base v3. Le BRIEF-4 part à Dev après la v2.1 du cahier et la fin de la passe 3b.
- 18 nov. 02:38 (Sources) : MOMR de déc. 2026 le 14 déc., donc P5 gelée le 8 déc. à 09:00, inchangé. Vague 1 : rien de bloquant (licences GASTAT/SAMA [à confirmer]). PMI S&P : usage interne seulement, aucune valeur PMI redistribuée dans les rapports. Écart FMI–GASTAT instable (change de signe en 2024) : pas de conversion fixe ; b_s à forte variance et écart affiché. P10 : gel avant la sortie de l'IPI de novembre (au plus tard le 8 janv. à 23:59).
- 18 nov. 02:40, CALENDRIER DE GEL CORRIGÉ (PMI de novembre publié le 3 déc. à 07:15, vérifié dans couverture_vague1_et_candidats.md, plus la règle des 48 h) : P17 tout de suite ; **P1 le 30 nov. à 23:59** ; P7 le 6 déc. à 09:00 ; P3 le 7 déc. à 09:00 ; P9 le 8 déc. à 09:00 ; **P5 le 11 déc. à 23:59** (MOMR le 14 déc., heure [à confirmer]) ; P10 le 8 janv. à 23:59 ; P11, P12, P14, P15 le 29 déc. à 09:00 ; P6 avant le 25 janv. ; P8, P13, P16 avant le 10 févr. Le moteur doit savoir figer avant le 30 nov. Repli minimal (persistance v3, figée et hachée) déclenché si l'import des vagues avec vérification du hash n'est pas fonctionnel le **26 nov.** Licence S&P : à régler avant toute version vendable (roadmap du deck).
- 18 nov. 02:42, vague 2 (chiffrage v2 4e5e831b…f20c, provisoire) : n_eff de la vague 11,80, λ̄ 0,1125, cumul des vagues 1 + 1b + 2 à 10,53. Décisions : N8 retirée ; règle (h) comptée par publication (même émetteur, même document, même date ; les produits EIA distincts sont des publications distinctes mais plafonnés par le facteur énergie) ; N5 et N6 étiquetées par Modèle, en « moyen » en cas de doute, et si les deux sont moyennes on garde N6 ; vivier d'au moins 20 séries pour les vagues 3 et 4 commandé à Sources. Durée retenue pour le deck : 30 vers fin janv. ou début févr. 2027 ; 50 avec résultats entre mi-juin et fin sept. 2027.
- 18 nov. 02:44 : N5 en « moyen », N6 en « faible », les deux gardées ; M2b reportée à la vague 3 ; le remplaçant de N8 doit être « faible ». CORRECTION de la durée pour le deck : point d'étape à 30 questions effectives TRANCHÉES vers mars 2027 (le gel de la vague 6 ou 7 a lieu fin janv. ou début févr.) ; conclusion à 50 entre juin et sept. 2027, selon la corrélation entre vagues mesurée.
- 18 nov. 02:46, FORMULATION DÉFINITIVE pour le deck (vague2_neff_Modele_v2.md, ligne 30, choix prudent) : « point d'étape à 30 questions effectives tranchées d'ici début mai 2027 ; conclusion à 50 entre mi-juin et fin sept. 2027, selon la corrélation entre vagues mesurée ». Elle remplace « vers mars 2027 ».
