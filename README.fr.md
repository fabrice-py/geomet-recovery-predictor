# Simulateur géométallurgique de flowsheet

*[English version](README.md)*

Un simulateur de traitement du minerai fondé sur la physique, écrit en Python avec une
interface Streamlit. Il prédit le comportement d'un minerai à travers des circuits
configurables de séparation, de comminution et de classification y compris les circuits
fermés avec charge circulante, résolus par itération de point fixe.

Chaque paramètre machine a un effet réel et physiquement fondé sur le résultat. Ce n'est pas
un outil jouet : il est conçu pour se comporter comme un véritable simulateur de procédés, où
modifier l'énergie d'un broyeur, la pression d'un cyclone ou la pente d'une table change
réellement le résultat.

## Points forts

- **Circuits multi-voies** : composez un flowsheet étage par étage, chaque étage utilisant une
  voie différente (gravité, magnétique, flottation, comminution, classification), avec ses
  réglages propres et son métal suivi.
- **Granulométrie complète (PSD)** : une vraie distribution de tailles traverse tout le modèle.
  La grille de classes est éditable par l'utilisateur ; le P80 est *dérivé* de la PSD.
- **Broyeur à boulets (loi de Bond)** : une unité de transformation qui broie un flux plus fin
  (P80 réduit, libération améliorée) selon l'énergie spécifique et l'indice de travail du
  minerai.
- **Hydrocyclone** : classification par taille en surverse (fines) et sousverse (grossiers),
  avec courbe de partage de Tromp ; le flux qui continue est sélectionnable.
- **Charge circulante** : un moteur de flowsheet à graphe résout les circuits fermés (ex.
  broyeur + cyclone en boucle) par la méthode du tear stream / point fixe, avec détection de
  convergence et de divergence. La masse globale est conservée au régime permanent.
- **Données de caractérisation réelles** : chargez une PSD mesurée, une DRX (minéralogie), une
  XRF (chimie globale, comparée à la chimie reconstruite) et un MEB (libération mesurée par
  minéral, remplaçant l'estimation dérivée du P80). Saisie manuelle et import CSV pour chacune.
- **Interface bilingue** (français / anglais) avec clés techniques et libellés d'affichage
  découplés.
- **Tests automatisés** (pytest) couvrant la conservation de masse (séparation, circuits série,
  cyclone, charge circulante) et les invariants physiques.

## Ce que fait le simulateur

À partir d'un minerai, un profil prédéfini, une composition de minéraux de base, ou une
minéralogie entièrement personnalisée le simulateur construit un flux d'alimentation portant
la masse, la minéralogie modale, la distribution de l'or par mode, l'état de libération et la
distribution granulométrique. Ce flux est ensuite acheminé à travers le flowsheet composé par
l'utilisateur.

Chaque séparation propage masse, minéralogie, chimie et modes d'or vers un concentré et un
rejet. La comminution transforme la distribution de tailles et améliore la libération. La
classification répartit le flux par taille. Lorsque le circuit contient une boucle, le moteur
itère jusqu'à ce que la charge circulante se stabilise. Des courbes teneur–récupération et de
cinétique sont disponibles par étage.

## Une conception à deux niveaux

L'outil sépare partout la **donnée** de la **logique** :

- Les minéraux, profils de minerai et propriétés minérales sont de la *donnée* (stœchiométrie,
  densités, comportement magnétique et flottabilité), pas de la logique codée en dur.
- Un registre de spécifications de séparation définit les paramètres réglables de chaque machine
  et leurs bornes, pilotant automatiquement l'interface et validant les entrées.
- Les libellés d'affichage sont découplés des clés techniques : l'interface se lit proprement
  dans deux langues tandis que le moteur travaille toujours sur des clés stables.

## Installation & utilisation

Nécessite Python 3.11+ et les paquets de `requirements.txt` (Streamlit, NumPy, pandas,
matplotlib).

```bash
# créer/activer un environnement, puis :
pip install -r requirements.txt
streamlit run app.py
```

Composez un minerai et un traitement dans la barre latérale et le panneau principal, puis
lancez la simulation. Pour un circuit fermé, ajoutez un « retour » d'étage à étage dans le
mode multi-voies.

## Architecture

- `data_models.py` : l'objet central `Stream` (solides, minéralogie modale, libération, P80,
  PSD, pulpe) et `LiberationState`.
- `mineralogy.py`, `mineral_properties.py` — données minéralogiques (stœchiométrie, profils de
  minerai, propriétés physiques).
- `separation.py` : le registre `SEPARATION_SPECS` et l'opération commune `separate`.
- `laws_gravity.py`, `laws_magnetic.py`, `laws_flotation.py` : les lois de réponse physiques.
- `size_classes.py` : grille de tailles et PSD (génération Rosin–Rammler, dérivation du P80).
- `comminution.py` : broyeur à boulets (loi de Bond).
- `classification.py` : hydrocyclone (point de coupure, partage de Tromp).
- `circuit.py` : moteur de circuit série.
- `flowsheet.py` : moteur de flowsheet à graphe (résolution topologique, itération de point
  fixe par tear stream pour la charge circulante).
- `i18n.py` : traductions et aides aux libellés.
- `app.py` : l'interface Streamlit.
- `tests/` : suite pytest (conservation de masse et invariants physiques).

## Posture de modélisation (limites assumées)

C'est un modèle **phénoménologique** : les lois de réponse capturent le bon *sens* de chaque
effet et des *ordres de grandeur* réalistes, mais elles **ne sont pas calibrées sur des essais
industriels spécifiques**. Plusieurs constantes (constante de coupure du cyclone, flottabilité
de l'or natif, densités des porteurs d'or, indice de travail par défaut, seuil de
convergence) sont des valeurs à caler sur données réelles, documentées comme telles. La valeur
de l'outil réside dans sa structure couplée de bout en bout où chaque paramètre se propage
de façon cohérente dans le flowsheet non dans une précision industrielle des prédictions.

## Travaux futurs

- **Libération par association minéralogique** : les associations MEB sont déjà collectées ; le
  prochain grand chantier de modélisation les fera influencer le comportement gravimétrique,
  de flottation et magnétique des particules mixtes (remplaçant l'approximation de libération
  scalaire).
- Calibration des constantes sur données mesurées.
- Physique d'hydrocyclone enrichie (effet de densité, apex/vortex finder).
- Éditeur de connexions complet optionnel pour des topologies quelconques (le moteur est déjà
  générique ; seule l'interface serait étendue).

## Auteur

Fabrice TSAMO -Iingénieur des Mines / Géométallurgie.
GitHub : [fabrice-py](https://github.com/fabrice-py)
LinkedIn account : www.linkedin.com/in/fabrice-tsamo