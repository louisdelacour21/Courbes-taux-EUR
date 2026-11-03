# Courbes de taux EUR multi-courbes et pricer de swaps

Bootstrapper une courbe d'actualisation €STR et une courbe de projection EURIBOR 6M, pricer un portefeuille
de swaps (DV01, risques par pilier, PnL explain), le tout reproduit à l'identique par QuantLib.

Fiche projet : `projets-cv/fiches/pdf/09-courbes-taux-swaps.pdf` (dossier Application Linkedin).

## Avancement

| # | Étape | État |
|---|-------|------|
| 1 | Moteur de dates comparé jour par jour à QuantLib (2000-2060) | fait |
| 2 | Données BCE, reconstitution, `hypotheses.md` | fait |
| 3 | Courbe €STR log-linéaire, Newton global | fait |
| 4 | Banc QuantLib €STR (écarts < 1e-10 en CI) | fait |
| 5 | Courbe EURIBOR 6M + banc QuantLib | fait |
| 6 | Hagan-West + leave-one-out | fait |
| 7 | NSS | fait |
| 8 | Pricer, buckets, couverture, IRRBB | fait |
| 9 | PnL explain | fait |
| 10 | Démo, synthèse du matin, rapport de validation | fait (mise en ligne à faire) |

## Moteur de dates (`courbes/dates.py`)

- Calendrier **TARGET2** (week-ends, 1er janvier, Vendredi saint, lundi de Pâques, 1er mai, 25 et 26 décembre).
- Conventions de jour ouvré : following, modified following, preceding, modified preceding, non ajusté.
- Ténors (`"2D"`, `"1W"`, `"6M"`, `"10Y"`) avec règle de fin de mois.
- Décompte des jours : ACT/360, ACT/365F, 30/360 Bond Basis.
- Échéanciers générés à rebours depuis la maturité (stub court en tête), avec ou sans fin de mois.

**Validation** (`tests/test_dates.py`, 48 tests) : comparaison à QuantLib sur chaque jour de 2000 à 2060
(jours ouvrés, ajustements, fins de mois), sur des milliers de ténors, de paires de dates et
d'échéanciers tirés au hasard (graine fixe). Aucun écart toléré.

Écart de comportement noté : avec la règle de fin de mois, QuantLib 1.44 ajuste les dates intermédiaires
à partir du dernier jour *calendaire* du mois ; en convention following, un 31 octobre tombant un dimanche
devient donc le 1er novembre. Le moteur reproduit ce comportement.

## Données (`courbes/donnees.py`, `courbes/cotations.py`)

> Niveaux reconstitués le 01/11/2026 ; validation QuantLib indépendante de la provenance ; études d'interpolation
> et PnL explain sur données synthétiques.

`data/cotations.csv` contient un an de cotations quotidiennes (€STR, OIS 1W-30Y, dépôt 6M, FRA, IRS 2Y-30Y contre
6M). Elles sont reconstituées à partir de séries BCE gratuites (courbe AAA, €STR, EURIBOR 6M mensuel), car aucune
source gratuite ne publie de cotations de swaps. Méthode, hypothèses et impact estimé : [`hypotheses.md`](hypotheses.md).
Le même format accepte de vraies cotations (`source = reel`).

## Courbe €STR (`courbes/curves.py`, `courbes/instruments.py`)

- Inconnues : x_k = ln P(T_k), un pilier par OIS (dernière date pertinente = dernier paiement, J+1 ouvré).
- Interpolation log-linéaire en t = ACT/365F, forward constant au-delà du dernier pilier.
- **Newton global** à jacobien analytique : la courbe renvoie des nombres duaux (valeur + gradient) que les
  formules des instruments propagent exactement. Arrêt à max|taux implicite − cotation| < 1e-13.
- Le jacobien dR/dx est conservé pour les risques par pilier (étape 8).

**Validation** (`tests/test_curves.py`) :
- repricing au pair à moins de 1e-13 sur un jour sur dix de l'année de cotations ;
- jacobien égal aux différences finies à 1e-6 près ;
- sur cotations non bruitées, la courbe retombe sur la courbe génératrice aux piliers (~1e-6 jusqu'à 10 ans).
  Entre deux piliers éloignés (25-30 ans), le log-linéaire s'en écarte jusqu'à ~2e-3 en DF : c'est ce que
  l'étape 6 doit mesurer.

**Banc QuantLib** (`tests/test_quantlib_estr.py`, écart toléré 1e-10) : la même courbe est construite avec
`OISRateHelper` (spot 2, paiement J+1 MF TARGET, fin de mois, pilier `LastRelevantDate`) et
`PiecewiseLogLinearDiscount` en ACT/365F (précision du bootstrap 1e-14). Les jours testés sont un sur dix, tous ceux dont le
spot tombe en fin de mois, et le dernier. Pour chacun, le banc compare :
- les piliers ;
- les facteurs d'actualisation sur 500 dates jusqu'à 40 ans ;
- les taux au pair des instruments de calage ;
- 200 OIS aléatoires (`MakeOIS.fairRate`, départ décalé jusqu'à 5 ans, ténor de 1W à 30Y).

Deux conventions comptent pour obtenir des écarts de l'ordre de 1e-15 :
- l'échéancier se génère depuis la maturité **non ajustée** (spot + ténor) ;
- quand le spot est un dernier jour ouvré du mois, la maturité est reportée au dernier jour du mois (règle de fin de mois).

## Courbe EURIBOR 6M (`courbe_euribor6m`)

- Instruments : dépôt 6M, FRA 1x7 à 18x24 (ACT/360, MF fin de mois), IRS 3Y-30Y (fixe annuel 30/360 Bond Basis,
  variable semestriel ACT/360, fin de mois, maturité non ajustée comme l'OIS).
- L'IRS 2Y est écarté : son pilier coïncide avec celui du FRA 18x24 (QuantLib refuse aussi deux piliers égaux).
- Actualisation exogène sur la courbe €STR (CSA cash EUR) ; même Newton global, la courbe €STR restant fixe.
- Coupon variable « au pair » (réglage par défaut de QuantLib) : forward 6M sur la période de calcul.

**Banc QuantLib** (`tests/test_quantlib_euribor6m.py`, écart toléré 1e-10, mêmes jours que le banc €STR) :
`DepositRateHelper`, `FraRateHelper`, `SwapRateHelper` actualisé sur la courbe €STR QuantLib. Le banc compare les piliers,
les facteurs d'actualisation 6M sur 500 dates, les taux au pair et 200 swaps aléatoires (`MakeVanillaSwap.fairRate`,
départ décalé jusqu'à 5 ans, ténor de 1 à 30 ans). Écarts observés de l'ordre de 1e-15.

## Hagan-West et choix d'interpolation (`CourbeHW`, `etudes/leave_one_out.py`)

**Hagan-West monotone convexe** (Hagan & West, 2006), sur les mêmes inconnues x_k = ln P(T_k) :
- forward instantané continu ; ∫f conservée sur chaque intervalle (les DF aux piliers valent exactement exp(x_k)) ;
- quatre régions selon l'écart du forward aux nœuds au forward discret, sans oscillation ;
- **contrainte de positivité désactivée** : inutile en taux positifs, nuisible en taux négatifs ;
- au-delà du dernier pilier, le dernier forward discret est prolongé, comme en log-linéaire et dans QuantLib ;
- Newton global démarré sur la solution log-linéaire (identique au bootstrap séquentiel), arrêt à 1e-13.
  Construction de la courbe €STR : ~0,15 s.

Le jacobien reste analytique (nombres duaux), mais Hagan-West n'est pas dérivable aux frontières de régions. À court
terme, les écarts g valent ~1e-6 : un choc de 1e-6 change de région, et les différences finies s'écartent du jacobien.
Le test utilise donc un choc de 1e-9.

**Banc QuantLib** (`tests/test_hagan_west.py`) : `PiecewiseConvexMonotoneForward` avec
`ConvexMonotone(quadraticity=0, monotonicity=1, forcePositive=False)` reproduit nos courbes €STR et 6M à ~1e-14.
La tolérance n'a pas eu besoin d'être relâchée : elle reste à 1e-10. Avec les réglages par défaut de QuantLib
(0,3 / 0,7 / positivité forcée), l'écart monte à ~1e-4 en DF : la méthode « pure » de l'article n'est pas le défaut de QuantLib.

Autres tests :
- G(1) = 0, g(0) = g0 et g(1) = g1 dans les quatre régions ;
- courbe plate exacte ;
- conservation de ∫f, continuité aux nœuds et forward positif sur le jeu de l'article. Ce jeu (zéros à 0,1 / 1 / 4 /
  9 / 20 / 30 ans) est repris de mémoire et n'a pas été vérifié contre les tableaux publiés.

**Leave-one-out** ([`etudes/leave_one_out.md`](etudes/leave_one_out.md)) : 30 jours (un sur dix + les 5 jours du
saut de base de l'IRS 10Y), cotations bruitées. Pour chaque jour, chaque instrument intérieur est retiré, la courbe est
reconstruite, puis l'erreur de pricing de l'instrument retiré est mesurée. Écarts en bp :

| Courbe | Interpolation | Moyenne | Max | Rugosité (bp²/an) |
|---|---|---|---|---|
| €STR | log-linéaire | 1,36 | 5,46 | 4,7 |
| €STR | Hagan-West | **0,32** | **1,37** | **0,7** |
| 6M | log-linéaire | 2,02 | 12,69 | 8,9 |
| 6M | Hagan-West | **0,62** | **3,70** | **1,1** |

**Choix de production : Hagan-West.** L'erreur moyenne est divisée par 3 à 4 et le maximum par 3 à 4. Le gain le plus
net porte sur les FRA (6x12 à 18x24 : 5 bp contre 1 bp en moyenne). La rugosité est divisée par 6 à 8.

Deux réserves :
- Les cotations dérivent d'une courbe Svensson lisse, ce qui avantage une interpolation lisse. Le classement reste à
  confirmer sur de vraies cotations.
- Hagan-West n'est pas locale. Les jours du saut, l'IRS 10Y retiré est moins bien repricé (max 3,1 bp contre 2,4 bp) :
  le saut se diffuse aux voisins. La non-localité des buckets est mesurée à l'étape 8 (section suivante) ; le log-linéaire
  reste disponible (`classe=Courbe`).

## NSS (`courbes/nss.py`, `etudes/nss.py`)

Nelson-Siegel-Svensson, formule de la BCE, taux zéro en capitalisation continue :
y(τ) = β0 + β1 L(τ/λ1) + β2 [L(τ/λ1) − e^{−τ/λ1}] + β3 [L(τ/λ2) − e^{−τ/λ2}], avec L(u) = (1 − e^{−u})/u.
**Usage : lissage, lecture niveau / pente / courbure et extrapolation, jamais pricing** (le pricing reste sur les
courbes bootstrapées, qui repricent les instruments à 1e-13).

- β par moindres carrés ordinaires à (λ1, λ2) fixés ; (λ1, λ2) par une grille de départ puis `scipy.optimize.least_squares`.
- Contraintes d'identification : 2 λ1 ≤ λ2 ≤ 30 ans (ordre de la BCE : τ1 ≈ 3 ans, τ2 ≈ 13 ans). Sans elles, l'optimum
  glisse vers λ1 ≈ λ2 : les deux bosses deviennent colinéaires et β2 ≈ −β3 atteint ±1e3, pour le même RMSE.

**Contrôle de la formule** (`tests/test_nss.py`) : les taux zéro BCE publiés (séries SR_3M, 1Y, 5Y, 10Y, 30Y, un an)
sont reproduits depuis les paramètres BCE à moins de 0,01 bp. Ce contrôle valide la formule, pas l'ajustement. S'y
ajoutent un aller-retour sans bruit (paramètres retrouvés, zéros à 1e-7 jusqu'à 40 ans) et un bruit de 1 bp
correctement mesuré par le RMSE.

**Ajustement aux zéros bootstrapés** ([`etudes/nss.md`](etudes/nss.md)) : chaque jour, NSS est ajusté aux zéros
Hagan-West des piliers €STR et 6M.

| Courbe | Cotations | RMSE moyen (bp) | RMSE max (bp) | Résidu max (bp) |
|---|---|---|---|---|
| €STR | bruitées | 0,55 | 1,86 | 6,17 |
| 6M | bruitées | 0,67 | 1,87 | 6,02 |
| €STR | sans bruit (1 jour sur 10) | 0,44 | 1,61 | 5,46 |
| 6M | sans bruit (1 jour sur 10) | 0,50 | 1,70 | 5,34 |

- Même sans bruit, le RMSE reste à ~0,5 bp : les zéros bootstrapés ne sont pas exactement une courbe Svensson. Le bruit
  n'ajoute que ~0,1 à 0,2 bp. Le RMSE mesure donc surtout l'erreur de forme de NSS ; les résidus max (5-6 bp) montrent
  pourquoi NSS ne doit pas servir au pricing.
- **Stabilité** : le zéro 10 ans bootstrapé varie de 3,4 bp par jour (écart-type), mais les β varient de 50 à 290 bp et un
  λ saute de plus de 50 % un jour sur dix environ (19 jours en €STR, 32 en 6M). Les contraintes ont divisé ces sauts par
  3 (59 et 79 sans contraintes) et ramené les variations de β de ~1e8 bp à ~1e2 bp, pour +0,1 bp de RMSE. Les paramètres
  restent trop instables pour être lus seuls au jour le jour.
- **Extrapolation à 40 ans** : NSS est en moyenne 5,5 bp sous le dernier forward prolongé des courbes bootstrapées
  (de −17 à +16 bp selon les jours).

## Pricer et risques (`courbes/pricing.py`, `courbes/risque.py`, `etudes/risque.py`)

Swap payeur : V = N [Σ τ_j F_j Pd(t_j) − K Σ τ_i Pd(t_i)], F_j projeté sur la courbe 6M, actualisation €STR. Le
portefeuille (`data/portefeuille.csv`) compte dix swaps : payeurs et receveurs, départs décalés, swaps en cours de vie.
**Les fixings EURIBOR 6M passés sont construits par hypothèse** : cotation DEPOT 6M reconstituée du jour de fixing.

- **Buckets** : ∂V/∂q = (∂V/∂x) J⁻¹, avec J = ∂R/∂x le jacobien global des deux courbes (x = [x_€STR, x_6M],
  triangulaire par blocs), obtenu par nombres duaux. Résultat en EUR par bp de cotation, en 0,1 s.
- **DV01** publié deux fois : par cotations (±1 bp, rebootstrap complet) et par taux zéro (+1 bp sur les zéros des
  deux courbes). Ils diffèrent d'environ 4 % (36 256 contre 37 593 EUR/bp).
- **Couverture** : h = −B⁻¹δ en instruments de calage au pair ; B est diagonale (annuité × 1 bp), calculée sans le
  supposer. Résidu ~1e-12 EUR/bp.
- **IRRBB** (BCBS 2016, EUR) : six chocs sur les taux zéro des deux courbes, plancher EBA post-choc
  max(r + Δ, min(r, −150 + 3t bp)), revalorisation complète. Pire scénario : parallèle bas, ΔEVE −9,6 M€. Les chocs par
  maturité sont exportés pour le projet 04 (stress tests) : [`etudes/chocs_irrbb.yaml`](etudes/chocs_irrbb.yaml).

**Contrôles** (`tests/test_risque.py`, en log-linéaire et Hagan-West) :
- swap au pair à 1e-10 × N ;
- NPV des dix swaps identiques à QuantLib (`MakeVanillaSwap`, `DiscountingSwapEngine`) à 1e-10 × N ;
- buckets égaux aux bumps de cotation (1e-7 relatif en log-linéaire). En Hagan-West, l'écart va jusqu'à ~1e-5 relatif :
  l'interpolation n'est pas dérivable aux frontières de ses régions ;
- Σ buckets = DV01 parallèle à 1e-3 ;
- portefeuille couvert à buckets nuls ;
- formules des chocs et du plancher.

**Localité** ([`etudes/risque.md`](etudes/risque.md)) : un swap spot de ténor coté a ses dates sur les piliers, donc
mêmes buckets dans les deux interpolations. Le P10Y-2024 (échéance 15/03/2034, entre les piliers 7Y et 8Y) répartit
28 % de ses |buckets| hors IRS 7Y/8Y en Hagan-West contre 9 % en log-linéaire, dont −5 257 EUR/bp sur l'IRS 9Y (0 en
log-linéaire). C'est le prix de la meilleure interpolation constatée à l'étape 6 : une couverture Hagan-West mobilise
plus d'instruments.

## PnL explain (`courbes/pnl.py`, `etudes/pnl.py`)

**Marché synthétique** : cotations reconstituées et bruitées, fixings EURIBOR 6M reconstitués. Le résultat valide la
mécanique de décomposition, pas un comportement de marché.

PnL(t → t+1) = portage + fixings + Σ_k bucket_k Δq_k + ½ Γ Δq̄² + résiduel :
- **portage** : courbes de t portées en t+1 (P(d) / P(t+1)), traduites en cotations q_c et rebootstrapées ; fixings
  tombés dans [t, t+1[ pris aux forwards ; flux payés inclus ;
- **fixings** : écart des fixings publiés à ces forwards. **Composante construite par hypothèse** (fixings
  reconstitués) ;
- **delta** : buckets des courbes portées × (q_1 − q_c) ; **gamma** : gamma parallèle (±1 bp, rebootstrap) × Δq̄².

Sur 254 jours en Hagan-West ([`etudes/pnl.md`](etudes/pnl.md), série dans
[`etudes/pnl_serie.csv`](etudes/pnl_serie.csv)) : résiduel moyen 4,9 % du PnL moyen en valeur absolue, médiane
jour par jour 3,2 %, 99,6 % de la variance du PnL expliquée. Le résiduel vient de la non-dérivabilité de Hagan-West
(changement de région de la monotone convexe) : le témoin log-linéaire tombe à 0,26 %. Pire jour : le saut de base
de l'IRS 10Y (2026-05-04). Par analogie seulement, c'est l'esprit du test d'attribution de PnL de FRTB (PnL
théorique contre PnL des facteurs de risque).

**Contrôles** (`tests/test_pnl.py`, deux interpolations) : résiduel nul en portage pur ; résiduel d'ordre 3 sur un
choc parallèle connu (rapport 8 entre chocs de 10 et 5 bp) ; flux payés.

L'étude a révélé un défaut corrigé : sur 33 jours, la fin du FRA 18x24 et celle de l'IRS 2Y diffèrent d'un jour, et
la courbe 6M gardait les deux (jacobien quasi singulier, buckets de ±1 M EUR/bp qui se compensent). Un IRS à 5 jours
près d'un pilier de FRA est désormais écarté.

## Démo, synthèse du matin, rapport (`app/`, `courbes/synthese.py`, `etudes/rapport.py`)

> Niveaux reconstitués depuis les données publiques BCE ; validation QuantLib indépendante de la provenance ;
> études d'interpolation et PnL explain sur données synthétiques.

**Démo Streamlit** : `streamlit run app/streamlit_app.py`. Onglets courbes (forwards 6M log-linéaire contre
Hagan-West), risques (buckets, swaps, IRRBB), PnL explain (série précalculée), synthèse du matin, études de validation.
Les courbes du jour choisi sont construites à la volée (quelques dixièmes de seconde) ; le PnL explain, 10 minutes de
calcul, est lu dans `etudes/pnl_serie.csv`.

**Synthèse du matin** : `python -m courbes.synthese [AAAA-MM-JJ]` (dernier jour par défaut). Valeur, DV01, trois plus
gros piliers, PnL explain de la veille et alertes : |résiduel| > max(10 % du PnL, 10 000 EUR), ou cotation qui bouge de
plus de 2 bp par rapport à la moyenne de ses deux voisines (mouvement isolé, comme le saut de base de l'IRS 10Y). **Temps
de calcul mesuré : environ 3 s** (2,6 à 3,1 s selon les lancers : deux jours de courbes, buckets et décomposition du PnL). Au 2026-05-04, la synthèse lève
l'alerte résiduel et les alertes IRS 9Y / IRS 10Y.

**Rapport de validation** : `python etudes/rapport.py` produit `rapport/rapport_validation.pdf` (HTML converti par Edge
headless). C'est une **auto-revue**, pas une validation indépendante au sens de SR 11-7. Le script recalcule chaque seuil
chiffré : repricing (< 1e-13) et écarts aux facteurs d'actualisation QuantLib (< 1e-10) sur les jours du banc, pour les
deux interpolations, puis la part du résiduel du PnL explain ; il reprend les études telles quelles.

Derniers chiffres (38 jours du banc, 28 s) :

| Interpolation | Repricing max | DF €STR max contre QuantLib | DF 6M max contre QuantLib |
|---|---:|---:|---:|
| Log-linéaire | 3,4e-14 | 4,5e-15 | 6,5e-14 |
| Hagan-West | 9,5e-14 | 3,0e-13 | 1,4e-13 |

PnL explain : 4,93 % (témoin log-linéaire 0,26 %) ; 30 jours sur 254 dépassent le seuil d'alerte du résiduel.

## Lancer les tests

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Licence MIT (`LICENSE`). Outils gratuits et open source uniquement (Python, NumPy, pandas, QuantLib, pytest) et données publiques BCE.
