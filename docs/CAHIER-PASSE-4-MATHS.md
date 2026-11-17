# Data IA – Cahier maths de la passe 4 (cible continue)
Auteur : Data IA · Modèle, 18 nov. 2026 (heure de Riyad, UTC+3). Statut : **v2.1 — intègre les réponses de l'orchestrateur au §9 et les compléments tirés de `couverture_vague1_et_candidats.md` ; à transmettre à l'orchestrateur, puis à Dev (BRIEF-4)**. v2 conservée : `CAHIER-PASSE-4-MATHS.v2.md`. v1 conservée : `CAHIER-PASSE-4-MATHS.v1.md`.

### Changelog v2 → v2.1
- §1 : arrondi au plus proche à une décimale, θ* = 4,45, **PROVISIONAL** jusqu'à confirmation par Sources du format publié par GASTAT ; le paramètre `rounding` reste en config ; première estimation = flash T4 2027.
- §7b : base naïve de la cible sur les **premières publications** ; principale = (k+1)/10 **y compris 2020** ; variante sans 2020 ((k′+1)/9) en sensibilité (on ne retire pas un choc réel d'une base de 8 ans) ; si les premières publications sont introuvables, millésime actuel étiqueté comme tel.
- §2–3 : millésimes datés FMI/Banque mondiale demandés à Sources ; tant qu'ils manquent, a priori de classe conservé et écrit.
- §2–3 : écart de définition FMI « non-oil GDP » / GASTAT « non-oil activities » : n'est **pas stable** (en première publication, changement de signe en 2024) ; pas de conversion fixe ; affiché dans le rapport ; b_s du FMI et de la Banque mondiale avec variance a priori **large** (CONVENTION : κ0 plus petit / s0 plus large que pour une source de classe comparable ; pas de chiffre inventé au-delà de « large »). Source : `/workspace/data-ia/couverture_vague1_et_candidats.md`.
- §5 et §10 : poids du bridge dans le groupe γ plafonné à 1/3 (config) tant que cov(u_bridge, u_FMI) n'est pas estimée ; à réexaminer au backtest.
- §7c : COORDINATION ne mentionne plus Beta(2,2) ; la référence de persistance est la base v3 (`/workspace/review/persist_v3.py`).
- v2.1.1 : gels corrigés (COORDINATION, règle des 48 h) : P1 au plus tard le 30 nov. 2026 à 23:59 ; P5 au plus tard le 11 déc. 2026 à 23:59 (remplace le 8 déc.).
- §7c : gel de P5 (corrigé en v2.1.1 : 11 déc. 2026 à 23:59) — le MOMR sort le 14 déc. ; gel de P10 au plus tard le 8 janv. 2027 à 23:59 (heure de Riyad, UTC+3), avant la publication de l'IPI de novembre.
- §2 et §10 : PMI S&P / Riyad Bank : usage interne seulement ; aucune valeur PMI dans un rapport.
- §7c et §9 : page Produit à corriger (P6 ancrée sur l'OPEC MOMR ; 0,5 seulement en dernier recours) — point clos.
- §9 : les 7 questions ouvertes deviennent le bloc **Décisions v2.1**, avec les compléments ci-dessus. §8 et §10 mis à jour en conséquence.

### Changelog v1 → v2
- §1 : arrondi θ* = 4,45 VALIDÉ par Recherche pour tout arrondi au plus proche (demi supérieur ou demi pair) ; seule une troncature donnerait 4,5. Révision (Y₁, release_rank = 1) VALIDÉE.
- §3b–c : **σ²_η n'est plus compté deux fois** (prioritaire) : NIG ajusté sur e − η̂_t ; terme commun σ²_η/T ajouté à la variance de Σw b̂ ; contrainte E[η] = 0 explicite.
- §3d : estimateur de σ²_γ corrigé (cov intra-groupe − cov groupe/hors groupe) ; ρ_g implicite remplacé par un raisonnement matriciel.
- §4 : s² = GLS sur Σ = σ²_γ·11ᵀ + diag(V), puis + σ²_η et σ²_η/T (au lieu de + σ²_γ entier) ; **P de référence par Monte Carlo** ; Student-t gardée pour les sensibilités ; garde-fou ν > 2.
- §5 : bridge = ridge à signes imposés, erreur décomposée η̂_t + u_bridge, bridge dans un groupe γ avec FMI/Banque mondiale, poids plafonné.
- §7b : base de la cible = **décision orchestrateur** : fréquence 2018-2025 (Laplace (k+1)/10, variante sans 2020 (k′+1)/9), FMI au seuil affiché comme référence (pas comme base).
- §7c : base par question tranchée par l'orchestrateur (persistance v3 pour P1, P3, P5, P9, P11, P12, P14 ; fréquence pour les autres).
- §7d : R construite par modèle à facteurs (PSD), forme pondérée Σσ_iσ_jR_ij, bootstrap par grappes + wild cluster ; P11/P12 à ρ = 1 ; P5–P6 même série.
- Nouveau §7e (n_eff vague 1 = 4,40) et §7f (règles vague 2, renvoi à vague2_neff_Modele.md).
- Nouveau §10 : liste priorisée pour Dev. §8–9 mis à jour.
Bases : COORDINATION.md (fait foi), page Produit (canvas 6ceaaf62, lue dans le store), liste VALIDÉE de la passe 3, note d'état de l'art, verify_p3.py, BRIEF-3 et BRIEF-3b (déjà couverts, pas repris ici), snapshot 03d0299.
Règle : chaque point est un **résultat attendu** suivi d'un **test d'acceptation**. Aucun chiffre n'est inventé. [à confirmer] = donnée à fournir par Sources ou Produit. CONVENTION = réglage provisoire, non calibré.

## 1. Formalisation de la cible
- **Résultat.** On note Y₁ la croissance annuelle réelle des « Non-oil activities » 2027, en %, telle qu'imprimée dans la **première** estimation annuelle GASTAT (**décision orchestrateur : flash du PIB T4 2027**, attendue vers le 1er févr. 2028 [à confirmer] ; question annulée si rien n'est publié avant le 31 mars 2028). θ = 4,5 et « at least », donc l'égalité donne OUI.
- **Arrondi.** On résout sur le chiffre imprimé au dixième : OUI ⇔ round(Y₁, 1) ≥ 4,5. **Décision orchestrateur :** arrondi au plus proche à une décimale, d'où θ* = 4,45 et P = P(Y₁ ≥ 4,45) [VALIDÉ Recherche pour tout arrondi au plus proche, demi supérieur ou demi pair : différence seulement aux égalités exactes, de probabilité nulle]. Seule une troncature donnerait θ* = 4,5. θ* = 4,45 est **PROVISIONAL** jusqu'à confirmation par Sources du format publié par GASTAT. Ce sont des paramètres de config `resolution: {threshold: 4.5, op: ">=", decimals: 1, rounding: half_up}`, et θ* est dérivé de la config, jamais écrit en dur.
- **Révisions.** La question se tranche sur la première estimation. La variable prédite est donc Y₁ et non le chiffre final. Tous les historiques d'erreurs se calculent contre les **premières publications**, jamais contre le millésime actuel. Les révisions ne servent qu'au nowcast (§3c).
- **Test.** Avec un même (μ, s), le moteur donne P(≥ 4,5 ; décimales 1, half_up) = 1 − F((4,45 − μ)/s). Un test vérifie aussi que, sans arrondi ou avec `rounding: truncate`, on obtient θ* = 4,5. La config refuse une question qui n'a pas `decimals` ou `rounding`.

## 2. Données nécessaires (à collecter par Sources)
| Donnée | Rôle | État |
|---|---|---|
| Premières publications GASTAT de la croissance « non-oil activities », annuelle et trimestrielle (flash), avec date de publication | Réalisés Y₁ pour les erreurs, base naïve, nowcast | Flashs en PDF (liens sur la page Produit) ; profondeur de l'historique des **premières** publications [à confirmer] |
| Millésimes datés des prévisions de croissance non pétrolière : FMI (WEO, Article IV), Banque mondiale, déclaration pré-budgétaire du MoF | f_{s,h} | Demandés à Sources (**décision orchestrateur**) ; série non pétrolière dans les jeux WEO via API [à confirmer] ; Article IV en PDF ; prévisions Banque mondiale hors API Indicators [à confirmer] ; chiffre non pétrolier du MoF [à confirmer] ; tant qu'ils manquent, a priori de classe conservé et écrit (§3c) |
| Indicateurs M1 à M8 (arbre Produit, ILLUSTRATIVE), avec date de publication et millésime | Variables explicatives du nowcast | Voir la page Produit ; PMI S&P / Riyad Bank : **usage interne seulement**, aucune valeur PMI dans un rapport (licence S&P) ; plusieurs sources ne sont qu'en PDF |
| Calendrier des publications GASTAT | h et `published_at` | Lien sur la page Produit ; dates [à confirmer] |
- **Écart de définition** FMI « non-oil GDP » / GASTAT « non-oil activities » : n'est **pas stable** (en première publication, l'écart va de −0,2 à +0,8 pt et change de signe en 2024 ; source : `/workspace/data-ia/couverture_vague1_et_candidats.md`). Aucune conversion fixe n'est défendable. L'écart est affiché dans le rapport et traité comme un biais de source b_s, avec une variance a priori large pour le FMI et la Banque mondiale (§3) (**décision orchestrateur**).
- **Règle de rapport PMI.** Le PMI S&P / Riyad Bank est à usage interne seulement : aucune valeur PMI n'apparaît dans un rapport (**décision orchestrateur**).
- **Test.** Toute ligne porte `published_at`, `vintage`, `release_rank` (1 = première publication) et `data_label`. Une erreur calculée contre une ligne où `release_rank ≠ 1` est refusée.

## 3. Modèle d'erreur et estimation
- **(a) Structure.** e_{s,h} = f_{s,h} − Y₁ = b_s + η_h + γ_{g(s),h} + u_{s,h}. η_h est le choc commun à toutes les sources pour une année donnée. γ_g est une composante de groupe, nulle hors groupe, pour les sources qui partagent les mêmes entrées. u est l'erreur propre à la source. **Identification :** b_s et η ne sont identifiables qu'avec la contrainte E[η] = 0 (η centré par construction). L'écart de définition FMI « non-oil GDP » / GASTAT « non-oil activities » n'est pas stable (changement de signe en première publication en 2024) : pas de conversion fixe ; il est traité comme un biais b_s et affiché dans le rapport (**décision orchestrateur**). Pour le FMI et la Banque mondiale, la variance a priori de b_s est **large** (CONVENTION : κ0 plus petit, ou s0 plus large, que pour une source de classe comparable ; pas de chiffre inventé au-delà de « large »). Les tranches d'horizon h, en mois avant la publication qui tranche, sont fixées en CONVENTION : > 18, 12-18, 6-12, 3-6, < 3.
- **(b) Par source : NIG complet, ajusté sur les erreurs nettes du choc commun.** On ajuste le NIG de chaque source sur ẽ_{s,t} = e_{s,t} − η̂_t, où η̂_t = moyenne transversale des erreurs de l'année t (sources présentes cette année-là), **pas sur e brut** : sur e brut, le NIG estime σ²_η + σ²_u (1,495 au lieu de 1,0 dans verify_p4.py), puis σ²_η est rajouté une seconde fois en §4. Avec ẽ on obtient 1,001. Alternative acceptée : modèle à effets aléatoires conjoint (b_s, η_t, u). Paramètres : (b0 = 0, κ0 = 2, ν0 = 4, s0² = k(classe)·σ²_ref,u(h), avec k : A 0,5 / B 1 / C 1,25 / D 2, appliqué **seulement** à σ²_u), terme croisé inclus. Poids w_s ∝ 1/V_s, avec V_s = σ²_n·ν_n/(ν_n−2)·(κ_n+1)/κ_n, la variance prédictive propre à la source. Le facteur (κ_n+1)/κ_n compte déjà l'incertitude propre sur b̂_s : ne pas la rajouter une seconde fois. En revanche, les b̂_s sont corrélés entre sources via η̂ (corr(b̂₁, b̂₂) = 0,332 simulé, 1/3 théorique) : Var(Σw_s b̂_s) contient un **terme commun σ²_η/T** qui ne diminue pas avec le nombre de sources (Davies & Lahiri 1995, https://doi.org/10.1016/0304-4076(94)01649-K). Tout est CONVENTION ; σ²_ref est à mesurer.
- **(c) Choc commun.** σ²_η(h) reçoit un a priori scaled-inv-χ²(ν_η, s²_η,0) tiré de l'historique des millésimes WEO contre les premières publications (valeurs [à calculer], PROVISIONAL tant que non mesurées). **Décision orchestrateur :** tant que les millésimes datés FMI et Banque mondiale ne sont pas obtenus, on garde cet a priori de classe et on l'écrit. L'a posteriori se calcule sur T années. Les ddl de la Student-t d'approximation valent ν = ν_η + T, **avec ν > 2 imposé** (sinon erreur). Avec peu d'années, σ²_η est mal identifié : c'est voulu, et la Student-t le reflète.
- **(d) Groupe corrélé M3/M4/M5 (décision Produit).** On n'utilise pas de ρ fixé à la main. Si ces moteurs servent de **régresseurs** dans le nowcast (cas nominal, §5), leur corrélation est absorbée par une régression bayésienne régularisée (ridge ou a priori normal), et il n'y a pas de n_eff. S'ils servent de **sources** de prévision, la composante γ_g est estimée : **σ̂²_γ = cov moyenne intra-groupe − cov moyenne groupe/hors groupe** (la cov intra seule estime σ²_η + σ²_γ : 0,798 pour 0,8 vrai ; l'estimateur corrigé donne 0,298 pour 0,3), tronquée à 0, avec un a priori inverse-gamma. On ne résume pas le groupe par un ρ_g scalaire (il suppose des σ²_u égaux) : on raisonne sur la matrice Σ_g = σ²_γ·1_g1_gᵀ + diag(V_s) (§4). Tant qu'on a moins de [CONVENTION 8] trimestres communs, le groupe compte pour une seule source (ρ = 1, choix prudent). ρ est borné à [−1/(n−1), 1], et un groupe sans paramètre lève une erreur.
- **Tests.**
  - Simulation depuis le modèle génératif : couverture des intervalles à 50 et 90 % dans la tolérance Monte Carlo.
  - k copies exactes d'une source ne changent ni μ ni s.
  - Poids w ≥ 0.
  - Un ρ estimé sur données simulées (ρ vrai connu) tombe dans un IC90 qui couvre la vraie valeur ≈ 90 % du temps.
  - Une table k non monotone ou ν0 ≤ 2 est refusée (déjà en 3b, à garder vert).
  - **(prioritaire)** Données simulées avec σ²_η = 1, σ²_u = 1 : σ̂²_u ne contient pas σ²_η (estimé ≈ 1,0 ± tolérance MC, pas ≈ 1,5).
  - Simulation avec σ²_η = 0,5, σ²_γ = 0,3 : σ̂²_γ ≈ 0,3 (pas 0,8).
  - Var(Σw b̂) simulée ≈ formule incluant σ²_η/T (tolérance MC).

## 4. Fusion → loi prédictive → probabilité
- **Résultat.**
  - μ = Σ_s w_s (f_s − b̂_s) + ajustement de nowcast (§5).
  - **Poids GLS** sur Σ = σ²_γ·1_g1_gᵀ (blocs par groupe) + diag(V_s) : w = Σ⁻¹1/(1ᵀΣ⁻¹1), projetés sur w ≥ 0 (si un poids est négatif : moindres carrés sous contrainte w ≥ 0, Σw = 1, variance sandwich wᵀΣw). Sans groupe, on retrouve w_s ∝ 1/V_s (Clemen & Winkler 1985, https://doi.org/10.1287/opre.33.2.427).
  - s² = wᵀΣw + σ²_η(h) + σ²_η(h)/T. **Ne pas ajouter σ²_γ en entier** (exemple verify_p4 : vraie variance 0,308, formule v1 0,500, GLS 0,279). L'incertitude propre sur b̂ est déjà dans V_s ((κ_n+1)/κ_n) ; seul le terme commun σ²_η/T s'ajoute.
  - **Probabilité de référence par Monte Carlo** (10⁵ à 10⁶ tirages, graine fixée et journalisée) : σ²_η ~ a posteriori scaled-inv-χ², η ~ N(0, σ²_η(1+1/T)), terme sources ~ t multivariée de matrice Σ ; P = part des tirages Y₁ ≥ θ*. Un mélange de t n'est pas une t (verify_p4 : MC 0,6404 contre t 0,6377 au seuil ; P(Y ≥ 6,5) 0,0491 contre 0,0513).
  - **Approximation Student-t** (ν > 2 imposé), position μ, échelle σ_t = s·√((ν−2)/ν) : sert aux sensibilités analytiques et au contrôle ; P_t = 1 − F_ν((θ* − μ)/σ_t).
  - On publie μ, s, ν, les quantiles 5/50/95 et P.
- **Sensibilités analytiques** (sur l'approximation t ; P publiée = MC), avec z = (θ* − μ)/σ_t et f la densité de la Student :
  - ∂P/∂μ = f(z)/σ_t ;
  - ∂P/∂f_k = w_k·f(z)/σ_t ;
  - ∂P/∂b̂_k = −w_k·f(z)/σ_t ;
  - ∂P/∂σ_t = f(z)·z/σ_t.
- **Tests.**
  - Cas calculé à la main : deux sources, σ²_η connu ; on doit retrouver μ, s et P exactement.
  - |P_t − P_MC| < 0,01 au seuil θ* (sinon alerte journalisée, P_MC fait foi).
  - ν ≤ 2 lève une erreur (l'échelle √((ν−2)/ν) n'existe pas).
  - Groupe de 2 sources identiques en γ : wᵀΣw égale le calcul matriciel à 1e-12 ; poids toujours ≥ 0.
  - Les sensibilités analytiques concordent avec les différences finies à pas relatif (erreur relative < 1e-4) pour z ∈ {−3, 0, 3}.
  - Pour ν → ∞, on retrouve le cas gaussien.
  - P est monotone en μ.

## 5. Place de l'arbre Produit (M1 à M8)
- **Résultat.**
  - Pour la racine continue, **pas d'agrégation logit**. Les moteurs alimentent une **équation de passage** (bridge) qui prédit la croissance non pétrolière trimestrielle : **ridge avec signes imposés** dans le sens annoncé par Produit (Baffigi et al. 2004, https://doi.org/10.1016/S0169-2070(03)00067-0 ; Giannone et al. 2008, https://doi.org/10.1016/j.jmoneco.2008.05.010). En mode régresseur, le ridge gère la colinéarité M3-M5 ; la règle « M3-M5 comptent pour une source » ne vaut qu'en mode source.
  - Sa sortie entre comme une source de plus, f_{bridge,h}. Sa variance d'erreur vient d'un backtest hors échantillon, **jamais** de l'ajustement dans l'échantillon. L'erreur du bridge est décomposée en η̂_t + u_bridge et **seule la variance de u_bridge** entre dans V_bridge (sinon η est compté deux fois).
  - Le FMI et la Banque mondiale utilisent déjà ces indicateurs : le bridge est placé **dans un groupe γ avec eux**, et son poids est **plafonné à 1/3** (**décision orchestrateur**, paramètre de config) tant que cov(u_bridge, u_FMI) n'est pas estimée ; à réexaminer au backtest.
  - Quand les flashs trimestriels 2027 arrivent, Y₁ s'écrit comme la moyenne des croissances trimestrielles sur un an, pondérée par les niveaux 2026. Pondération exacte [à confirmer] avec la méthode GASTAT. Les trimestres publiés entrent avec leur variance de révision vers la première estimation annuelle ; seuls les trimestres restants sont prévus.
  - Les poids vivent en config, aucun n'est codé en dur (y compris le plafond 1/3).
  - L'agrégation logit (avec le paramètre global a et la recalibration neutre σ(α + γL)) reste réservée aux questions **binaires** composées.
- **Tests.**
  - Si les quatre trimestres sont publiés, s² se réduit à la seule variance de révision.
  - Un coefficient de signe contraire à celui annoncé est ramené à 0 (contrainte active journalisée).
  - V_bridge ne contient pas σ²_η (même test que §3).
  - Retirer un moteur ne change P que par sa sensibilité, tracée au tableau de bord.
  - La validation de l'équation de passage n'utilise que des observations où `published_at` est antérieur à l'origine de la prévision.

## 6. Controller et surprise sur la même loi
- **Résultat.**
  - Controller : résidus r_s = f_s − b̂_s − μ_(−s), où μ_(−s) est la fusion sans s. On les compare à une Student-t prédictive dont la variance vaut V_s + Var(μ_(−s)). La quarantaine se décide **par source**.
  - Surprise : −log de la densité prédictive (μ_{t−1}, s_{t−1}, ν) en x_t = x̂ fusionné. On n'utilise qu'un historique où `as_of` est strictement antérieur à t. Pas de cas spécial sous 3 points : l'a priori de classe prend le relais.
  - Un seul seuil α sert aux deux mécanismes.
- **Tests.**
  - En simulation sous H0, le taux de faux rejets et d'alertes vaut α ± la tolérance Monte Carlo (ref. verify_p3 : le plug-in actuel donne 15,6 % à 25,7 %).
  - Une valeur aberrante injectée met en quarantaine sa seule source.
  - Une observation datée de t ou après est refusée.

## 7. Preuve
- **(a) Backtest de la cible, à origine glissante.**
  - Pour chaque année passée disponible (2018-2025, sous réserve des millésimes) et chaque tranche h, on reconstruit la prévision avec les seules données publiées avant l'origine (`published_at` < origine), en temps réel.
  - Scores : CRPS (forme fermée de la Student), score logarithmique, histogramme PIT, Brier à θ* et aux seuils voisins θ ± 0,5 et ± 1 (CONVENTION), BSS, bootstrap apparié par **année**. Les horizons d'une même année ne sont pas indépendants.
  - Bases : fréquence 2018-2025 (base principale, §7b) ; FMI dernier millésime seul, lu comme une t centrée de variance historique (référence affichée) ; persistance (croissance de l'année précédente, contrôle).
  - Avec 8 années au plus, ce backtest est un **diagnostic, pas une preuve**. Il est étiqueté « non interprétable » tant que n_eff < 30 (seuil de BRIEF-3).
- **(b) Base naïve de la cible (décision orchestrateur, COORDINATION v3, précisée en v2.1).**
  - Calculée sur les **premières publications** (cohérent avec la résolution). Si les premières publications ne sont pas trouvées, on prend le millésime actuel, étiqueté comme tel.
  - **Base principale : fréquence 2018-2025, y compris 2020**, règle de Laplace (moyenne a posteriori Beta(1,1) sur n = 8), soit (k+1)/10, où k = nombre d'années 2018-2025 avec Y₁ ≥ 4,5 ([à calculer]). On ne retire pas un choc réel d'une base de 8 ans.
  - Variante sans 2020 ((k′+1)/9) affichée en **sensibilité** seulement.
  - **Référence affichée : FMI au seuil** (le seuil 4,5 est la prévision du FMI, d'où P ≈ 0,5 : base la plus exigeante). Proposée en base principale par Recherche ; l'orchestrateur a tranché : référence affichée seulement (la règle « jamais 0,5 » de COORDINATION reste).
  - Persistance en contrôle : OUI si le dernier chiffre annuel publié atteint 4,5. Le chiffre 2026 est attendu en févr. 2027 (P13).
  - Mise en garde écrite : 8 années, ruptures (2020, Vision 2030, changements de base GASTAT). Avec une seule réalisation 2027, la comparaison est un **diagnostic, pas une preuve** (Murphy 1992, https://doi.org/10.1175/1520-0434(1992)007%3C0692:CPATLC%3E2.0.CO;2).
- **(c) Questions de preuve de la vague 1 (P1 à P17, page Produit).**
  - Chacune porte sur un indicateur continu. On applique la même mécanique qu'aux §3-4 : Student-t prédictive de l'indicateur, puis P(X op θ) avec l'arrondi publié de chaque série (paramètre par question).
  - Seuils fixés au préenregistrement sur la dernière valeur publiée, jamais inventés. Prévision figée au plus tard 48 h avant la publication attendue. **Gels confirmés (heure de Riyad, UTC+3) :** P1 au plus tard le 30 nov. 2026 à 23:59 (PMI de novembre le 3 déc.) ; P5 au plus tard le 11 déc. 2026 à 23:59 (le MOMR sort le 14 déc.) ; P10 au plus tard le 8 janv. 2027 à 23:59, avant la publication de l'IPI de novembre.
  - **Base par question (décision orchestrateur) :** P1, P3, P5, P9, P11, P12, P14 → persistance v3 en base principale, fréquence en contrôle ; autres questions → fréquence historique. Cela remplace l'ancienne règle « fréquence sur 24 à 36 observations, sinon persistance » (contradiction relevée par Recherche). 0,5 seulement en dernier recours, avec une justification écrite (COORDINATION). L'orchestrateur a demandé à Produit de corriger sa page (P6 ancrée sur l'OPEC MOMR ; 0,5 seulement en dernier recours) : ce point est clos. Valeurs : `/workspace/data-ia/waves/vague1_bases.yaml` (en attente des séries capturées par Sources).
  - Questions « au-dessus de la dernière valeur » (P1, P3, P5, P9, P11, P12, P14) : base de référence = persistance probabiliste lissée, décidée par Modèle le 18 nov. : /workspace/review/base-persistance-probabiliste.md ; **référence de code : `/workspace/review/persist_v3.py`** (COORDINATION v3 ne mentionne plus Beta(2,2)). v3 : chaîne à deux états hausse / non-hausse, zéros comptés en non-hausse, p_haut = (u_d+4f)/(n_d+4) avec f = (h+1)/(m+2), K = 12, repli sur f si n < 6, une seule série fixée et hashée avant t0, millésime au data_cutoff, recalcul à chaque forecast_at, bornes [0,05 ; 0,95] ; f rapportée en contrôle, pas de conclusion si le modèle bat Markov mais pas f ; 30 questions effectives = étape intermédiaire, conclusion formelle ≥ 50, cible 100. Elle remplace la persistance pure 0/1 ; 0,5 et la fréquence lissée des hausses restent en contrôle.
- **(d) n_eff des questions de preuve (point d'étape ≥ 30 ; conclusion formelle ≥ 50, cible 100).**
  - Formule VALIDÉE (effet de plan de Kish 1965 généralisé) : n_eff = n²/Σ_{i,j} R_ij si les écarts de score ont la même variance ; sinon **n_eff = (Σσ_i)²/Σ_{i,j} σ_iσ_jR_ij**.
  - **R par modèle à facteurs**, R = LLᵀ + D, D ≥ 0 : un facteur par publication (deux questions de la même publication → R_ij = 1), un par moteur (ρ_drv CONVENTION), un facteur macro commun. PSD par construction. La convention v1 « 1 / ρ_drv / 0 » est abandonnée : elle peut être non PSD (A = B, B~C à 0,5, A,C à 0 → valeur propre −0,118).
  - Décisions orchestrateur : P11/P12 = groupe G_SAMA_BULLETIN à ρ = 1 ; ρ de P7 = 0,3 (errata E2) ; P5–P6 (vague 1b) : même série → facteur commun à ajouter quand P6 est intégrée.
  - ρ_drv et la charge macro seront estimés sur la corrélation des différences de score (plan préenregistré : vague2_neff_Modele.md §3).
  - **Bootstrap par grappes** = composantes connexes publication + moteur (hors facteur macro) ; **wild cluster bootstrap** s'il y a peu de grappes (Cameron, Gelbach & Miller 2008, https://doi.org/10.1162/rest.90.3.414).
  - Avec 17 questions, n_eff ≤ 17 : le seuil de 30 exige plusieurs vagues.
  - **Tests :** k questions indépendantes → n_eff = k ; 3 questions d'une même publication → n_eff = 1 ; n = 10, ρ = 0,3 → 2,7027 ; **R est PSD** (valeur propre min ≥ −1e-12, sinon erreur) ; forme pondérée = forme simple si σ_i égaux ; verdict « non interprétable » tant que n_eff < 30.
- **(e) n_eff de la vague 1 (`vague1.yaml`, SHA-256 36d214bb…2311 ; résultats dans `vague1_bases.yaml`, SHA-256 ed3b0714…df02d).**
  - **n_eff = 4,40 pour 15 questions** (4,11 sans P16), conventions de l'orchestrateur ; plage 3,6 à 6,1 pour des ρ réduits ou augmentés de 40 %. Script `/workspace/review/neff_vague1.py`, rapport `neff_vague1.md`.
  - Si les vagues étaient indépendantes : ~7 vagues pour 30, ~12 pour 50, ~23 pour 100. Si le facteur macro (c₀ ≈ 0,09) est commun à tout le pilote, le total **plafonne vers 11** quel que soit le nombre de vagues.
  - 6 grappes dont 3 singletons → wild cluster bootstrap. P6/P17 (vague 1b) non incluses ; à recalculer avec le facteur P5–P6.
- **(f) Règles de la vague 2 (proposition commune Modèle + Produit, envoyée à l'orchestrateur).** Détail : `/workspace/data-ia/waves/vague2_neff_Modele.md` (SHA-256 140ff858…4baa7), script `/workspace/review/neff_vague2.py`.
  - Mix type Produit (20 questions) : n_eff 7,7 par vague (6,0–9,7), charge macro moyenne λ̄ = 0,22 → plafond pessimiste ≈ 21 : 50 inatteignable si le choc macro est commun à tout le pilote.
  - Contrainte qui compte : **λ̄ ≤ 0,13** (budget Σλ_i ≤ 0,13·n ; λ = 0,1/0,3/0,5 pour lien faible/moyen/fort, CONVENTION), en plus de n_eff intra-vague ≥ 7, vérifiés avant gel. Part macro « fort » max ≈ 5 %, pas 30 %.
  - Durée réaliste : 30 en ~8–9 vagues bimensuelles (~5 mois), 50 en ~11–16 vagues (~6–9 mois), à condition que la corrélation entre vagues mesurée soit ≤ 0,02 ; si ≥ 0,05 après 4 vagues, 50 est déclaré inatteignable.
  - Plan préenregistré de σ_d et du plancher entre vagues : vague2_neff_Modele.md §3.

## 8. Ce qui reste PROVISIONAL, et ce qui est hors passe 4
- **PROVISIONAL :** κ0, ν0, table k, σ²_ref, a priori de σ²_η (a priori de classe conservé et écrit tant que les millésimes datés FMI/BM manquent), variance a priori large de b_s pour le FMI et la Banque mondiale (CONVENTION, sans chiffre au-delà de « large »), tranches d'horizon, ρ_drv, charges du modèle à facteurs (macro 0,1/0,3/0,5), σ²_γ avant estimation, seuils voisins, règle d'arrondi (au plus proche, θ* = 4,45, jusqu'à confirmation Sources du format GASTAT), pondération trimestrielle, nombre de tirages MC. Plafond du poids du bridge : 1/3 (décidé, à réexaminer au backtest).
- **Hors passe 4 :**
  - Bayes empirique à la Smyth sur toutes les sources ;
  - β par nœud en pooling hiérarchique ;
  - apprentissage de α et γ de la recalibration ;
  - oubli exponentiel et score de contribution ;
  - ruptures (CUSUM, BOCPD) et biais de régime ;
  - marchés de prédiction ;
  - réseau bayésien des moteurs.

## 9. Questions pour l'orchestrateur
Tranchées depuis la v1 : base de la cible (fréquence 2018-2025, FMI en référence) ; base par question de la vague 1 ; P11/P12 à ρ = 1 ; ρ de P7 = 0,3.

### Décisions v2.1
1. **Arrondi.** Arrondi au plus proche à une décimale : θ* = 4,45, **PROVISIONAL** jusqu'à confirmation par Sources du format publié par GASTAT. Le paramètre `rounding` reste en config. La première estimation est le flash T4 2027.
2. **Base naïve de la cible.** Sur les premières publications. La version principale inclut 2020, (k+1)/10 ; la variante sans 2020, (k′+1)/9, est affichée en sensibilité : on ne retire pas un choc réel d'une base de 8 ans. Si les premières publications ne sont pas trouvées, on prend le millésime actuel, étiqueté comme tel.
3. **Millésimes datés FMI et Banque mondiale.** Demandés à Sources. Tant qu'on ne les a pas, on garde l'a priori de classe et on l'écrit.
4. **Écart de définition** FMI « non-oil GDP » / GASTAT « non-oil activities » : n'est pas stable (en première publication, changement de signe en 2024) ; pas de conversion fixe ; affiché dans le rapport ; traité comme un biais b_s dont la variance a priori, pour le FMI et la Banque mondiale, est large (CONVENTION : κ0 plus petit / s0 plus large ; pas de chiffre inventé au-delà de « large »). Source : `/workspace/data-ia/couverture_vague1_et_candidats.md`.
5. **Plafond du poids du bridge** dans le groupe γ : 1/3 tant que cov(u_bridge, u_FMI) n'est pas estimée ; à réexaminer au backtest. Le plafond est un paramètre de config.
6. **Persistance.** COORDINATION ne mentionne plus Beta(2,2) : la référence est la base v3 (`/workspace/review/persist_v3.py`).
7. **Page Produit.** L'orchestrateur a demandé à Produit de corriger sa page (P6 ancrée sur l'OPEC MOMR ; 0,5 seulement en dernier recours). Ce point est clos.
8. **Gel de P5.** Au plus tard le 11 déc. 2026 à 23:59 (heure de Riyad, UTC+3), règle des 48 h (correction Produit consignée dans COORDINATION). Le MOMR sort le 14 déc. P1 : au plus tard le 30 nov. 2026 à 23:59.
9. **Gel de P10.** Au plus tard le 8 janv. 2027 à 23:59 (heure de Riyad, UTC+3), avant la publication de l'IPI de novembre.
10. **PMI S&P / Riyad Bank.** Usage interne seulement : aucune valeur PMI dans un rapport.

Plus aucune question de cette liste n'est ouverte.

## 10. Liste pour Dev (BRIEF-4), par priorité
1. **[P0] σ²_η compté deux fois** : ajuster le NIG de chaque source sur e_{s,t} − η̂_t (η̂_t = moyenne transversale des erreurs de l'année t), ou effets aléatoires conjoints ; test « σ̂²_u ne contient pas σ²_η ».
2. **[P0] Variance de fusion** : GLS sur Σ = σ²_γ·1_g1_gᵀ + diag(V), w ≥ 0 (moindres carrés contraints), s² = wᵀΣw + σ²_η + σ²_η/T ; supprimer « + σ²_γ » entier ; ne pas rajouter l'incertitude de b̂ déjà dans (κ_n+1)/κ_n.
3. **[P0] Estimateur σ²_γ** = cov intra-groupe − cov groupe/hors groupe, tronqué à 0.
4. **[P1] Probabilité par Monte Carlo** (10⁵–10⁶ tirages, graine journalisée) ; t pour les sensibilités ; test |P_t − P_MC| < 0,01 ; **garde-fou ν > 2** (erreur sinon), y compris dans σ_t = s·√((ν−2)/ν).
5. **[P1] n_eff** : R = LLᵀ + D (modèle à facteurs), test « R est PSD », forme pondérée Σσ_iσ_jR_ij, config P11/P12 ρ = 1, P5–P6 même série ; bootstrap par grappes + wild cluster.
6. **[P1] Bridge M1-M8** : ridge à signes imposés, variance hors échantillon, V_bridge = Var(u_bridge) seulement, bridge dans le groupe γ FMI/BM avec poids **plafonné à 1/3** (config) tant que cov(u_bridge, u_FMI) n'est pas estimée ; à réexaminer au backtest.
7. **[P2] Bases** : cible = fréquence 2018-2025 sur les premières publications, principale (k+1)/10 y compris 2020, variante sans 2020 ((k′+1)/9) en sensibilité ; si premières publications introuvables, millésime actuel étiqueté comme tel ; FMI au seuil affiché ; vague 1 = persistance v3 (`persist_v3.py`) pour P1, P3, P5, P9, P11, P12, P14, fréquence sinon (lire `vague1_bases.yaml`) ; corriger `naive_baseline_order`.
8. **[P2] Résolution** : arrondi au plus proche à une décimale (défaut `half_up`), θ* = 4,45, **PROVISIONAL** jusqu'à confirmation Sources du format GASTAT ; config `rounding` accepte `half_up`, `half_even`, `truncate` ; θ* dérivé, jamais en dur ; première estimation = flash T4 2027.
9. **[P2] Rapport et a priori :** écart de définition FMI/GASTAT affiché (pas de conversion fixe ; écart non stable, signe inversé en 2024 en première publication) ; b_s du FMI et de la Banque mondiale avec variance a priori large (CONVENTION, κ0 plus petit / s0 plus large, sans chiffre inventé au-delà de « large ») ; a priori de classe de σ²_η écrit tant que les millésimes datés FMI/BM ne sont pas obtenus.
10. **[P1] Règle de rapport PMI :** usage interne seulement du PMI S&P / Riyad Bank ; **aucune valeur PMI dans un rapport**.
11. **[P2] Gels (heure de Riyad, UTC+3) :** P1 au plus tard le 30 nov. 2026 à 23:59 ; P5 au plus tard le 11 déc. 2026 à 23:59 (MOMR le 14 déc.) ; P10 au plus tard le 8 janv. 2027 à 23:59, avant l'IPI de novembre.
12. **Rappel passe 3 (toujours ouverts en 03d0299)** : χ² qui vaut toujours n ; dédoublonnage par origine ; surprise instable ; sensibilités par différences finies fausses près de 0/1 ; ddof = 0 et N = 1 → τ = 1e12 ; membre de groupe à τ = 0 compté dans n ; groupe sans ρ traité comme indépendant ; `config.py:35` vers un seed absent ; KeyError sur feuille en quarantaine (liste VALIDÉE : `passe3-liste-maths-VALIDEE.md`).
