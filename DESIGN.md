# Simulateur géométallurgique de récupération  : Cahier des charges

*[English version: DESIGN.en.md](DESIGN.en.md)*

> Document de conception (`DESIGN.md`). Fige l'architecture, le périmètre et la
> feuille de route du projet. Sert de ligne directrice unique pour le développement.

---

## 1. Vision du projet

L'outil n'est pas un simple « prédicteur » avalant trois attributs. C'est un
**simulateur géométallurgique piloté par la minéralogie et conscient de la voie de
séparation**. À partir de la caractérisation d'un minerai (teneurs, minéralogie
modale, libération, granulométrie) et d'un choix de procédé paramétré par
l'utilisateur, il prédit la **récupération**, la **cinétique** le cas échéant, et
reconstitue un **bilan matière-eau** cohérent.

Objectif de portfolio : démontrer une compréhension complète de la chaîne
géologie → minéralurgie, depuis la mesure jusqu'au flowsheet qui boucle, avec une
posture d'ingénieur honnête sur ce qui est validé et ce qui reste à calibrer.

---

## 2. Les deux sens de circulation des données

Point conceptuel central, à ne jamais confondre :

- **Le générateur** va `minéralogie → teneurs`. Sens physiquement causal : les
  minéraux portent les éléments. Pour *fabriquer* un gisement synthétique cohérent,
  on invente la minéralogie modale et on en déduit les dosages par stœchiométrie.
  Le générateur joue « la nature + le labo ».

- **Le prédicteur** (l'outil manipulé par l'utilisateur) va dans l'autre sens :
  l'utilisateur **apporte** des teneurs mesurées (XRF / ICP / fire assay) *et* une
  minéralogie mesurée (DRX + Rietveld), et l'outil prédit la performance par voie.

- **Le pont** entre les deux est la **réconciliation élément–minéral**
  (*element-to-mineral conversion*) : on ne fait jamais aveuglément confiance à
  l'un ou à l'autre, on résout par moindres carrés la déportation des éléments dans
  les phases pour rendre teneurs et minéralogie cohérentes (fermeture comprise).
  Ce module est une brique à part entière et un argument d'entretien fort.

---

## 3. Architecture en couches

Toute la logique se range en une pile, du mesuré vers le prédit :

1. **Mesures** : teneurs XRF / ICP / fire assay : la vérité chimique.
2. **Minéralogie modale** : proportions de phases (DRX + Rietveld), réconciliées
   avec la couche 1, somme = 100 % (contrainte de fermeture).
3. **Texture** : matrice d'**associations** entre phases (idéalement MLA/QEMSCAN)
   + **degré et maille de libération par minéral d'intérêt** (plusieurs éléments
   simultanés possibles : Au, Cu, Zn, Co…).
4. **Granulométrie** : PSD fournie par l'utilisateur.
5. **Propriétés intrinsèques** :  base de données par minéral : densité,
   susceptibilité magnétique, hydrophobicité/flottabilité native. Extensible.
6. **Moteur de séparation** : un modèle d'unité par voie, qui lit la base 5 et les
   réglages machine saisis par l'utilisateur.
7. **Liant** : la libération **module tout** : une particule mixte (composite) ne
   rapporte au concentré que partiellement. C'est la couche 3 qui gouverne le
   rendement du moteur 6.

Paradigme sous-jacent : **« particle-based »** (Lamberg) : on ne sépare pas des
éléments, on sépare des **particules** dont le comportement dépend de leur contenu
minéral et de leur degré de libération.

---

## 4. Le schéma de données : l'objet `Stream`

Un « échantillon » n'est plus une ligne de tableau mais un objet `Stream` qui
circule dans le circuit et s'additionne aux nœuds. C'est le contrat que tout le
reste respecte.

Conçu **Option A** (libération scalaire par minéral) avec des **hooks explicites
vers l'Option B** (libération particulaire / classes) : on changera *l'intérieur*
des objets sans casser *l'interface*.

```python
@dataclass
class LiberationState:
    degree: dict                      # {mineral: 0-1}      <- Option A (utilisé)
    classes: Optional[dict] = None    # {mineral: array}    <- hook Option B

@dataclass
class Stream:
    # solides
    solids_tph: float                 # débit de solides (t/h)
    modal: dict                       # {mineral: % masse}  (somme = 100)
    liberation: LiberationState
    p80_um: float                     # résumé granulo
    psd_curve: Optional[np.ndarray] = None   # hook PSD complète (B)
    # pulpe / eau
    pct_solids_mass: float = 35.0     # % solides massique
    # dérivés (calculés)
    assays: dict = field(default_factory=dict)   # {élément: %} reconstruit
    water_tph: float = 0.0
    pulp_sg: float = 0.0
```

Règles de conception :
- **Densité du solide non saisie** : calculée depuis la minéralogie par loi de
  mélange `1/ρs = Σ(wᵢ/ρᵢ)`. Un seul jeu de données (la base minérale) sert au
  bilan-eau ET au moteur gravimétrique.
- **Libération et granulométrie** suivent le même pattern : scalaire maintenant,
  distribution complète en réserve.

Deux objets légers complètent l'architecture : `SeparationUnit` (§6) et `Circuit`
(graphe de streams et d'unités, avec arête de recyclage).

---

## 5. Les profils de minerai (= de la donnée, pas du code)

Les « types de minerai » sont des profils extensibles. Ajouter un gisement = ajouter
un profil.

### 5.1 `iron_flotation` : ossature validable
Minerai de fer (hématite / magnétite / quartz). C'est le profil **calibré et validé
quantitativement** contre des données industrielles publiques réelles (§8).

### 5.2 `polymetallic_refractory_au` : extension de gamme
Minerai aurifère sulfuré réfractaire, type gisements d'Albiti : chalcopyrite (CuFeS₂),
sphalérite (ZnS), pyrite cobaltifère (FeS₂ + Co), arsénopyrite (FeAsS), gangue
silicatée. Génère Cu, Zn, Co, As, Fe, SiO₂ + Au.

Concept clé modélisé : **l'or réfractaire**. Une part de l'or est piégée dans le
réseau des sulfures (arsénopyrite, pyrite) → invisible à la gravimétrie/cyanuration,
récupérable seulement après flottation des sulfures. Modélisé en deux parts (libre /
réfractaire), la part réfractaire croissant avec la teneur en sulfures hôtes et avec
un broyage grossier.

Statut : **modèle de plausibilité physiquement motivé, non calibré** (pas de jeu
public MLA/QEMSCAN). Présenté comme tel. Sa fonction : démontrer que l'architecture
supporte un minerai complexe multi-éléments.

Contrainte technique : la minéralogie modale est tirée par une loi de **Dirichlet**,
qui garantit la fermeture à 100 % (données compositionnelles, Aitchison).

---

## 6. Le moteur de séparation

### 6.1 Principe : trois choses séparées, jamais mélangées

1. **Propriétés intrinsèques du minéral** (base de données, immuables) : densité,
   susceptibilité magnétique, hydrophobicité native.
2. **Paramètres de conduite machine** (saisis/choisis par l'utilisateur, propres à
   chaque unité).
3. **Loi de réponse** qui combine 1 et 2 pour sortir récupération / cinétique.

Le paramètre machine n'agit jamais seul : il **module** la façon dont la propriété
intrinsèque s'exprime (ex. l'inclinaison + la fréquence d'une table déplacent le
**d50** en densité ; c'est ce d50 croisé à la densité de la particule qui donne la
récupération).

### 6.2 Registre des paramètres de conduite

`SEPARATION_SPECS` = de la donnée : bornes + valeur par défaut par paramètre. Sert à
(a) valider les entrées utilisateur, (b) auto-générer une interface plus tard
(chaque paramètre borné → un slider). Ajouter une machine = ajouter une entrée, sans
toucher au moteur.

Paramètres retenus par voie :

| Voie | Paramètres de conduite (utilisateur) | Propriété intrinsèque pilote | Sortie modulée |
|---|---|---|---|
| **Flottation** (directe / inverse) | type de collecteur (xanthate/PAX/amine), dose collecteur (g/t), moussant (g/t), pH pulpe, temps de séjour | hydrophobicité / flottabilité | `k` et `Rmax` par minéral |
| **Magnétique** | mode (LIMS/WHIMS × humide/sec), champ (T), vitesse tambour (rpm) | susceptibilité massique | susceptibilité de coupure |
| **Gravimétrie – table à secousses** | inclinaison (°), fréquence de secousse (Hz), eau de lavage (L/min) | densité | `d50`, netteté `Ep` |

Notes physiques intégrées :
- Flottation **inverse** = on flotte la gangue silicatée à l'amine (sélectivité
  inversée) ; le **pH** pilote la sélectivité sulfures/pyrite → pile le cas
  réfractaire.
- Magnétique : **LIMS** (basse intensité → ferromagnétiques, magnétite) vs **WHIMS**
  (haute intensité → paramagnétiques, hématite/certains sulfures). Humide vs sec
  décale le seuil et l'entraînement hydraulique.

### 6.3 Périmètre implémenté (décision figée)

**Trois voies pleinement implémentées** avec leurs lois de réponse, couvrant trois
physiques distinctes :
1. Flottation (directe + inverse)
2. Magnétique (LIMS/WHIMS, humide/sec)
3. Gravimétrie :  table à secousses, Séparateur Falcon et Hydrocyclone

**Extensions déclarées** dans le registre mais non implémentées (visibles comme
axes d'évolution) : **concentrateur centrifuge type Falcon** (vitesse de rotation +
eau de fluidisation retenu comme extension prioritaire), spirale, MGS.

Principe : trois voies bien faites valent mieux que six bâclées.

### 6.4 Nature des lois de réponse (posture assumée)

Lois **semi-empiriques, phénoménologiques, à sensibilité physiquement correcte, non
calibrées** (faute de données d'essais par machine). On ne prétend pas prédire au
point près ; on garantit les **bons sens de variation** et les bons **ordres de
grandeur** (plus de collecteur → `k` monte puis plafonne ; broyage plus grossier →
`d50` gravité se dégrade). Différence assumée entre modèle phénoménologique honnête
et fausse précision. Documenté explicitement c'est ce qui reste à calibrer avec de
vrais essais.

---

## 7. Pulpe, eau, charge circulante et bilan matière

### 7.1 Ce qu'on modélise ici (Projet 1)
- Chaque `Stream` est **conscient de la pulpe** : solides + eau + % solides + SG.
- Densité solide du mélange par loi de mélange (§4).
- **Charge circulante analytique sur un circuit fermé simple** (broyage fermé sur
  cyclone, ou séparation avec recyclage) pour *démontrer* la fermeture du bilan.

Formules de référence :
- Charge circulante (marqueur granulo) : `CL ≈ (o − f) / (f − u)`
  (% passant alimentation `f`, surverse `o`, souverse `u`).
- Formule deux produits : récupération `R = c(f − t) / [f(c − t)]`,
  rendement pondéral `Y = (f − t)/(c − t)` (teneurs alim./concentré/rejet `f,c,t`).
- Eau : fermée par les `pct_solids` de chaque stream.

Livrable : un **tableau de bilan matière-eau qui boucle** (par stream : t/h solides,
t/h eau, % solides, teneurs, récupération cumulée).

### 7.2 Charge circulante : solveur général réalisé (dépassement du périmètre initial)

Le périmètre initial prévoyait de renvoyer le solveur général multi-nœuds au Projet 2
(mini-USIM PAC). **Ce solveur a finalement été construit dans ce projet.** La charge
circulante n'est plus traitée de façon analytique sur un cas simple : elle est résolue
par un **moteur de flowsheet à graphe générique** (`flowsheet.py`) capable de traiter
n'importe quelle topologie, y compris les boucles.

Principe du solveur :
- Le circuit est décrit en **nœuds** (unités) + **connexions** (quelle sortie alimente
  quel nœud). Une boucle est simplement une connexion vers un nœud amont.
- Un circuit **sans boucle** est résolu en une passe par **tri topologique**.
- Un circuit **fermé** est résolu par la **méthode du tear stream / point fixe** : on
  coupe les arêtes de retour, on les suppose vides, puis on itère en réinjectant le flux
  de retour estimé jusqu'à **stabilisation** du débit (convergence à un seuil).
- La **convergence** est surveillée finement : distinction entre convergence lente et
  vraie divergence (écarts croissants), plafond de charge circulante (10× l'alimentation),
  statuts explicites (`converged`, `diverged`, `circulating_load_too_high`, `max_iter_reached`).
- **Conservation de masse globale** vérifiée au régime permanent (test automatisé) : la
  charge circulante tourne en boucle sans créer ni détruire de masse.

L'interface (mode multi-voies) permet de composer une série d'étages puis d'ajouter des
**retours** (une sortie qui reboucle vers un étage antérieur), ce qui construit le graphe
en interne. Le moteur étant générique, une évolution future vers un éditeur de connexions
complet (topologies quelconques) ne demanderait que d'étendre l'interface, pas le moteur.

---

## 8. Stratégie de validation (deux niveaux)

C'est ce qui répond au problème « pas de données Eramet » de façon élégante.

- **Niveau 1 : données réelles (cas fer)** : le profil `iron_flotation` est calé et
  validé contre le jeu public **Kaggle *Quality Prediction in a Mining Process***
  (usine de flottation de fer réelle, ~737 k lignes, cible % silice concentré).
  Validation quantitative.

- **Niveau 2 : auto cohérence physique (cas polymétallique)** : le générateur
  connaît la « vérité » particule par particule, donc il simule la récupération
  *vraie*. Le prédicteur, lui, ne voit que la caractérisation limitée. On valide le
  prédicteur contre la vérité du générateur boucle auto-cohérente, sans données
  réelles.

Deux niveaux de preuve = posture d'ingénieur solide.

---

## 9. Limites assumées (section entretien)

À écrire noir sur blanc dans le README,  elles protègent et valorisent :
- Le profil polymétallique est un modèle de plausibilité **non calibré** (pas de
  jeu public MLA/QEMSCAN pour associations/libération par taille).
- Les valeurs stœchiométriques sont des approximations de manuel (sphalérite avec Fe
  en substitution, Co variable dans la pyrite…).
- Les lois de réponse machine sont **phénoménologiques** : sens de variation et
  ordres de grandeur corrects, pas de précision calibrée par essais.
- Aucune donnée propriétaire ou confidentielle utilisée.

---

## 10. Décisions de conception figées (récapitulatif)

| Sujet | Décision |
|---|---|
| Niveau de libération | **Option A** (scalaire par minéral), enrichie par la libération mesurée au MEB ; **Option B** (par associations) = prochain grand chantier |
| Voies implémentées | Gravité (table, spirale, Falcon), magnétique (LIMS/WHIMS, humide/sec), flottation (directe/inverse), broyeur à boulets (Bond), hydrocyclone (Tromp) |
| Granulométrie | PSD complète (Rosin–Rammler), grille éditable, P80 dérivé de la PSD ; traverse broyage et classification |
| Charge circulante | **Solveur général à graphe** (tear stream / point fixe), toutes topologies, convergence robuste le « Projet 2 » a été absorbé ici |
| Données réelles | Chargement PSD, DRX, XRF (avec comparaison), MEB (libération mesurée) ; saisie manuelle + CSV |
| Validation | Suite **pytest** : conservation de masse (séparation, circuit, cyclone, charge circulante) + invariants physiques |
| Profils | `iron_flotation`, `polymetallic_refractory_au`, `polymetallic_pb_cu_zn`, `polymetallic_au_cu_zn_pb` |

---

## 11. Feuille de route (état réel)

Le projet a dépassé son cahier des charges initial de 7 séances. État actuel :

**Réalisé :**
| Bloc | Contenu | État |
|---|---|---|
| Fondations | `Stream` complet (minéralogie → teneurs → pulpe), profils de minerai | ✅ |
| Propriétés minérales | Base densités / magnétisme / flottabilité + pulpe | ✅ |
| Moteur de séparation | Gravité (table/spirale/Falcon), magnétique (LIMS/WHIMS), flottation, piloté par libération et réglages machine | ✅ |
| Or multi-modes | Or natif / sulfures / gangue, recouvrement gravimétrique et par flottation, cascade selon le broyage | ✅ |
| Granulométrie (PSD) | Grille éditable, génération Rosin–Rammler, P80 dérivé, traverse tout le flowsheet | ✅ |
| Broyeur à boulets | Loi de Bond (énergie + indice de travail → réduction de P80 + libération) | ✅ |
| Hydrocyclone | Classification par taille, courbe de partage de Tromp, deux flux | ✅ |
| Charge circulante | Moteur de flowsheet à graphe, tear stream / point fixe, convergence robuste | ✅ |
| Données réelles | Chargement PSD, DRX, XRF (comparaison), MEB (libération mesurée) - manuel + CSV | ✅ |
| Interface | Multilingue FR/EN, habillage des libellés, sélection guidée des phases | ✅ |
| Tests | Suite pytest : conservation de masse + invariants physiques | ✅ |
| Documentation | README bilingue, DESIGN à jour | ✅ |

**À venir :**
| Bloc | Contenu |
|---|---|
| Libération par associations (Option B) | Les associations MEB (déjà collectées) influenceront gravité / flottation / magnétique des particules mixtes |
| Calibration | Caler les constantes phénoménologiques sur données mesurées |
| Raffinements | Hydrocyclone (effet densité, apex/vortex), CI (badge), script de lancement |

Chaque bloc se clôt par un `commit` + `push`.

---

## 12. Stack technique

Python 3.11 · NumPy · pandas · SciPy · scikit-learn · XGBoost · Matplotlib · seaborn
· Jupyter · pytest · ruff · (GitHub Actions en finition)

Environnement conda isolé : `geomet-recovery`.
