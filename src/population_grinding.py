"""Broyage par bilan de population (modele d'Austin), hybride avec la loi de Bond.

Principe : la loi de Bond (comminution.py) donne l'INTENSITE globale du broyage (combien
d'energie, donc combien de reduction au total). Ce module distribue cette reduction entre
les classes granulometriques selon la DISTRIBUTION DES TAILLES DE BOULETS, car chaque taille
de boulet casse efficacement une gamme de particules : ainsi la FORME de la PSD de sortie
depend de la charge de boulets, pas seulement le P80.

Brique 1 : la structure de la distribution de boulets (ce fichier debute ici)."""

# Distribution de boulets par defaut (charge d'equilibre type d'un broyeur secondaire).
# Cle = diametre de boulet (mm), valeur = proportion EN MASSE. Normalisee a l'usage.
DEFAULT_BALL_DISTRIBUTION = {80.0: 0.20, 60.0: 0.30, 40.0: 0.30, 25.0: 0.20}

# Densite de l'acier des boulets (g/cm3), car convertir une proportion massique en nombre de
# boulets exige leur masse individuelle (volume x densite) : ainsi la physique de sélection,
# qui compte les impacts, pourra raisonner par nombre plutot que par masse.
BALL_DENSITY_G_CM3 = 7.8


def normalize_distribution(distribution):
    """Normalise les proportions massiques d'une distribution de boulets a somme 1, car
    l'utilisateur peut saisir des proportions qui ne somment pas exactement a 1 (ou a 100) :
    ainsi on travaille toujours sur des fractions coherentes. Ignore les tailles <= 0."""
    clean = {float(d): float(p) for d, p in distribution.items() if float(d) > 0 and float(p) > 0}
    total = sum(clean.values())
    if total <= 1e-12:
        return dict(DEFAULT_BALL_DISTRIBUTION)   # garde-fou : distribution vide -> defaut
    return {d: p / total for d, p in clean.items()}


def ball_mass_g(diameter_mm):
    """Masse d'un boulet spherique (g) a partir de son diametre (mm), car la conversion
    masse->nombre en depend : volume = 4/3 pi r^3, masse = volume x densite."""
    import math
    r_cm = (diameter_mm / 10.0) / 2.0          # mm -> cm, puis rayon
    volume_cm3 = (4.0 / 3.0) * math.pi * r_cm ** 3
    return volume_cm3 * BALL_DENSITY_G_CM3


def mass_to_number_fractions(distribution):
    """Convertit des proportions MASSIQUES en proportions en NOMBRE de boulets, car a masse
    egale il y a beaucoup plus de petits boulets que de gros (un 80 mm pese ~32x un 25 mm) :
    ainsi la physique de selection, qui compte les impacts, raisonne sur le bon effectif.
    n_i proportionnel a (masse_i / masse_unitaire_i)."""
    norm = normalize_distribution(distribution)
    counts = {d: p / ball_mass_g(d) for d, p in norm.items()}   # nombre relatif par classe
    total = sum(counts.values())
    return {d: c / total for d, c in counts.items()}

# --- Brique 2 : fonction de selection S (quel boulet casse quelle particule) ---

# Parametres phenomenologiques du modele de selection (Austin), NON calibres sur essais.
# Documentes comme tels (posture honnete) ; a caler sur donnees reelles plus tard.
SEL_ALPHA = 1.0        # exposant de taille : la selection croit ~ x^alpha pour les fines.
SEL_LAMBDA = 3.0       # raideur du plafonnement pour les grosses particules.
SEL_K_MU = 0.05        # taille critique de particule / taille de boulet (mm) : un boulet casse
                       # bien jusqu'a ~1/20 de son diametre. mu(um) = SEL_K_MU * d(mm) * 1000.
# Vitesse de broyage relative du materiau actif (quartz = reference 1.0), posee par
# apply_material_preset. Vaut 1.0 par defaut, car sans preset choisi le broyage garde son
# comportement de reference.
MATERIAL_VITESSE_REL = 1.0
# work_index : Bond Work Index (kWh/t), la broyabilite (durete) du materiau, car en mode Bond
# c'est le Wi qui porte la durete : ainsi choisir un materiau agit de façon coherente sur les
# DEUX modes (Bond via Wi, population via SEL_* et vitesse). SOURCES Wi :
#   - marbre : ~11 kWh/t, proxy calcaire CaCO3 (BICO 10.8 / Sepor 12.2, academia 2022).
#   - quartz : ~13 kWh/t, BWI standard silice.
#   - coke : 13 kWh/t = defaut neutre (pas de BWI standard publie trouve pour le coke) -> indicatif.
MATERIAL_PRESETS = {
    "marbre": {"SEL_ALPHA": 0.92, "SEL_LAMBDA": 3.35, "SEL_K_MU": 0.146,
               "vitesse_rel": 1.89, "work_index": 11.0,
               "source": "Petrakis 2017 (forme) ; Wi proxy calcaire"},
    "quartz": {"SEL_ALPHA": 1.15, "SEL_LAMBDA": 3.15, "SEL_K_MU": 0.083,
               "vitesse_rel": 1.00, "work_index": 13.0,
               "source": "Petrakis 2017 (forme, reference) ; Wi BWI silice"},
    "coke":   {"SEL_ALPHA": 1.50, "SEL_LAMBDA": 3.00, "SEL_K_MU": 0.031,
               "vitesse_rel": 1.00, "work_index": None,
               "source": "Colorado-Arango 2021 (forme cale) ; Wi non publie -> saisi par l'utilisateur"},
}

def material_work_index(nom):
    """Renvoie le Bond Work Index (kWh/t) du preset materiau, ou None si 'personnalise' ou
    inconnu, car en mode preset le materiau impose sa durete (le Wi du preset ecrase le curseur) :
    ainsi le broyage Bond reflete la broyabilite du materiau choisi."""
    if nom in MATERIAL_PRESETS:
        return MATERIAL_PRESETS[nom].get("work_index")
    return None

def selection_by_ball(x_um, ball_mm):
    """Vitesse de cassure (selection) d'une particule de taille x_um par un boulet de diametre
    ball_mm, car chaque boulet casse efficacement une GAMME de particules :
    - la selection croit avec la taille de particule (x^alpha), les grosses etant plus fragiles ;
    - mais PLAFONNE puis chute quand la particule devient trop grosse pour le boulet (elle
      glisse au lieu d'etre saisie) : facteur Q = 1/(1 + (x/mu)^Lambda), ou mu ~ taille du boulet.
    Ainsi un GROS boulet a son maximum de selection sur de GROSSES particules, un petit sur les
    fines. Valeur relative (l'echelle absolue sera calee par l'energie de Bond)."""
    mu_um = SEL_K_MU * ball_mm * 1000.0            # taille critique de particule (um)
    croissance = x_um ** SEL_ALPHA                 # croit avec la taille
    plafond = 1.0 / (1.0 + (x_um / mu_um) ** SEL_LAMBDA)   # chute au-dela de mu
    return croissance * plafond

def apply_material_preset(nom):
    """Applique un preset de materiau en posant les constantes globales de selection, car ces
    constantes gouvernent la vitesse et la forme du broyage : ainsi choisir un materiau change
    le comportement (un marbre broie plus vite qu'un quartz). Modifie les globales du module ;
    renvoie le dict applique. Leve une erreur si le materiau est inconnu."""
    global SEL_ALPHA, SEL_LAMBDA, SEL_K_MU, MATERIAL_VITESSE_REL
    if nom not in MATERIAL_PRESETS:
        raise ValueError(f"Materiau inconnu : {nom}. Choix : {list(MATERIAL_PRESETS)}")
    preset = MATERIAL_PRESETS[nom]
    SEL_ALPHA = preset["SEL_ALPHA"]
    SEL_LAMBDA = preset["SEL_LAMBDA"]
    SEL_K_MU = preset["SEL_K_MU"]
    MATERIAL_VITESSE_REL = preset["vitesse_rel"]
    return preset

# Sauvegarde des valeurs par defaut des constantes de selection, car appliquer un preset modifie
# les globales et il faut pouvoir revenir a l'etat "personnalise" (non force) entre deux runs :
# ainsi on fige les defauts au chargement du module, une seule fois.
_DEFAULT_SEL_ALPHA = SEL_ALPHA
_DEFAULT_SEL_LAMBDA = SEL_LAMBDA
_DEFAULT_SEL_K_MU = SEL_K_MU
_DEFAULT_VITESSE_REL = MATERIAL_VITESSE_REL


def reset_material_defaults():
    """Restaure les constantes de selection a leurs valeurs par defaut (mode 'personnalise'),
    car les globales persistent entre appels : ainsi un preset choisi a un run precedent ne
    reste pas colle si l'utilisateur revient a 'personnalise' ou change de materiau."""
    global SEL_ALPHA, SEL_LAMBDA, SEL_K_MU, MATERIAL_VITESSE_REL
    SEL_ALPHA = _DEFAULT_SEL_ALPHA
    SEL_LAMBDA = _DEFAULT_SEL_LAMBDA
    SEL_K_MU = _DEFAULT_SEL_K_MU
    MATERIAL_VITESSE_REL = _DEFAULT_VITESSE_REL
def selection_total(x_um, distribution):
    """Selection TOTALE d'une particule de taille x_um par la charge de boulets DISTRIBUEE, car
    chaque taille de boulet contribue selon son EFFECTIF (nombre) : ainsi on somme les
    selections de chaque classe de boulet, ponderees par leur fraction en nombre.
    S_total(x) = somme_d [ n(d) * S(x, d) ]."""
    number_fracs = mass_to_number_fractions(distribution)
    return sum(n * selection_by_ball(x_um, d) for d, n in number_fracs.items())

# --- Brique 3 : fonction de broyage B (comment les fragments se redistribuent) ---

# Parametres phenomenologiques de la fonction de broyage (Austin), NON calibres (a caler).
BRK_PHI = 0.5      # ponderation entre le terme "fines" et le terme "gros fragments".
BRK_GAMMA = 0.6    # exposant du terme fines : plus il est bas, plus on produit de fines.
BRK_BETA = 4.0     # exposant du terme gros fragments : chute rapide pour les gros morceaux.


def breakage_cumulative(x_i, x_j):
    """Fonction de broyage CUMULEE B(x_i, x_j) : fraction de la masse issue de la cassure d'une
    particule de taille x_j qui se retrouve PLUS FINE que x_i, car une cassure produit un spectre
    de fragments (des fines et quelques gros morceaux) : ainsi B decrit la forme de ce spectre.
    Forme d'Austin a deux termes (normalisee : depend du rapport x_i/x_j) :
        B = phi*(x_i/x_j)^gamma + (1-phi)*(x_i/x_j)^beta
    B(x_i>=x_j) = 1 (toute la masse est plus fine que la particule mere), B croit quand x_i baisse."""
    if x_i >= x_j:
        return 1.0
    ratio = x_i / x_j
    return BRK_PHI * ratio ** BRK_GAMMA + (1.0 - BRK_PHI) * ratio ** BRK_BETA


def breakage_fraction(i, j, sizes):
    """Fraction de masse issue de la cassure d'une particule de classe j qui atterrit DANS la
    classe i (i plus fine que j), car le bilan de population raisonne classe par classe : ainsi
    on prend la difference des B cumulees entre les bornes de la classe i.
    sizes : tailles representatives des classes (decroissantes, sizes[0] = la plus grossiere).
    b(i,j) = B(borne_haute_i, x_j) - B(borne_basse_i, x_j)."""
    if i <= j:
        return 0.0   # une cassure ne produit que du PLUS FIN (i > j en indice = plus fin)
    # Bornes de la classe i : entre sizes[i] et sizes[i-1] (approximation par les tailles repr.).
    x_j = sizes[j]
    haut = sizes[i - 1] if i - 1 >= 0 else sizes[0]
    bas = sizes[i]
    return breakage_cumulative(haut, x_j) - breakage_cumulative(bas, x_j)

# --- Brique 4a : un pas de bilan de population (la matrice S+B transforme la PSD) ---


def grinding_step(psd, sizes, distribution, delta):
    """Applique UN pas de broyage a une PSD (bilan de population d'Austin), car le broyage
    transfere de la masse des classes grossieres vers les fines selon S (qui casse) et B (ou
    vont les fragments) :
        p_i(sortie) = p_i - S_i*p_i*delta + somme_{j<i} b_ij*S_j*p_j*delta
    - psd : liste des fractions massiques par classe (somme 1), index 0 = la plus grossiere.
    - sizes : tailles representatives des classes (decroissantes).
    - distribution : la charge de boulets (pour S total).
    - delta : intensite du pas (calee sur Bond en 4b). Doit rester petit pour la stabilite.
    Conservation de masse : ce qui quitte une classe est integralement redistribue dans les
    classes plus fines ; la DERNIERE classe absorbe tout le residu (fines sous la grille)."""
    n = len(psd)
    # Selection de chaque classe (bornée pour la stabilite : S*delta <= 1).
        # Selection normalisee : on ramene la selection maximale a 1, car les valeurs brutes de
    # selection_total sont en unites arbitraires ; ainsi delta controle directement l'intensite
    # du pas (fraction de la classe la plus 'cassable' qui casse a chaque pas).
    raw = [selection_total(sizes[i], distribution) for i in range(n)]
    s_max = max(raw) if raw else 1.0
    S = [min(1.0, (raw[i] / s_max) * delta) for i in range(n)]

    out = [0.0] * n
    for i in range(n):
        # Masse qui RESTE dans la classe i (non cassee).
        out[i] += psd[i] * (1.0 - S[i])
        # Masse qui QUITTE la classe i (cassee) et se redistribue dans les classes plus fines.
        broken = psd[i] * S[i]
        if broken <= 0:
            continue
        redistributed = 0.0
        for k in range(i + 1, n):
            frac = breakage_fraction_ball(k, i, sizes, distribution)
            out[k] += broken * frac
            redistributed += broken * frac
        # Residu (fragments sous la derniere classe) : absorbe par la classe la plus fine, car
        # la grille est finie et rien ne doit se perdre : ainsi la masse est conservee.
        residue = broken - redistributed
        if residue > 0:
            out[n - 1] += residue
    return out

# --- Brique 4b : hybridation avec Bond (iterer jusqu'au P80 cible de Bond) ---


def grind_psd_to_target(psd, sizes, grid, distribution, p80_target,
                        delta=0.05, max_steps=500):
    """Broie une PSD par bilan de population jusqu'a atteindre le P80 cible fixe par Bond, car
    Bond cale l'INTENSITE globale (energie -> P80) tandis que la matrice S+B donne la FORME :
    ainsi on applique des pas de broyage jusqu'a ce que le P80 courant atteigne la cible.
    - p80_target : le P80 vise, fourni par la loi de Bond (calibree).
    - delta : intensite de chaque pas (petit pour la finesse du calage).
    - max_steps : garde-fou contre une boucle infinie.
    Retour : (psd_broyee, p80_atteint, n_steps). La masse est conservee a chaque pas."""
    from size_classes import p80_from_psd
    current = list(psd)
    p80_current = p80_from_psd(grid, current)
    # Si la cible est deja atteinte ou plus grossiere, on ne broie pas (un broyeur ne grossit pas).
    if p80_target >= p80_current:
        return current, p80_current, 0
    steps = 0
    while p80_current > p80_target and steps < max_steps:
        current = grinding_step(current, sizes, distribution, delta)
        p80_current = p80_from_psd(grid, current)
        steps += 1
    return current, round(p80_current, 1), steps

# --- Etape piste A : calage sur l'ENERGIE (nombre de pas), la charge module le P80 atteint ---


def calibrate_steps_for_bond(psd, sizes, grid, p80_bond, reference_distribution=None,
                             delta=0.05, max_steps=500):
    """Calibre le NOMBRE DE PAS pour qu'une charge de REFERENCE atteigne le P80 de Bond, car
    l'energie de Bond doit correspondre a une quantite de broyage : ainsi on mesure combien de
    pas la charge de reference met pour atteindre le P80 de Bond. Ce nombre de pas represente
    l'ENERGIE appliquee ; une AUTRE charge, avec ce meme nombre de pas, atteindra un P80
    different selon son efficacite."""
    from size_classes import p80_from_psd
    if reference_distribution is None:
        reference_distribution = DEFAULT_BALL_DISTRIBUTION
    current = list(psd)
    p80_current = p80_from_psd(grid, current)
    if p80_bond >= p80_current:
        return 0
    steps = 0
    while p80_current > p80_bond and steps < max_steps:
        current = grinding_step(current, sizes, reference_distribution, delta)
        p80_current = p80_from_psd(grid, current)
        steps += 1
    return steps


def grind_psd_energy_based(psd, sizes, grid, distribution, p80_bond,
                           reference_distribution=None, delta=0.05):
    """Broie une PSD en appliquant l'ENERGIE de Bond (traduite en nombre de pas cale sur une
    charge de reference), car la charge REELLE module alors l'efficacite : ainsi une charge bien
    adaptee atteint un P80 plus fin que Bond, une charge mal adaptee un P80 plus grossier.
    Bond fixe l'energie de reference ; la distribution de boulets module le resultat.
    Retour : (psd_broyee, p80_atteint, n_steps)."""
    from size_classes import p80_from_psd
    # 1) Calibrer le nombre de pas sur une charge de reference (= l'energie de Bond).
    n_steps = calibrate_steps_for_bond(psd, sizes, grid, p80_bond, reference_distribution, delta)
    # 2) Moduler par la vitesse de broyage du materiau, car a energie de Bond egale un materiau
    # tendre (marbre) se reduit davantage qu'un materiau dur (quartz) : ainsi vitesse_rel etire
    # ou reduit le nombre de pas effectifs. Reference quartz = 1.0. La vitesse est portee par la
    # variable de module MATERIAL_VITESSE_REL, posee par apply_material_preset.
    n_effectif = max(1, int(round(n_steps * MATERIAL_VITESSE_REL)))
    # 3) Appliquer avec la charge REELLE.
    current = list(psd)
    for _ in range(n_effectif):
        current = grinding_step(current, sizes, distribution, delta)
    return current, round(p80_from_psd(grid, current), 1), n_effectif

# --- Piste B (option 1) : forme des fragments dependante des boulets qui cassent chaque classe ---

# Modulation de phi (ponderation fines/gros de B) selon la taille du boulet effectif :
# gros boulet -> phi BAS (impact violent, gros fragments) ; petit boulet -> phi HAUT (attrition,
# plus de fines). Bornes phenomenologiques a caler.
PHI_MIN = 0.30     # gros boulets : peu de poids au terme fines -> fragments plus grossiers.
PHI_MAX = 0.70     # petits boulets : plus de fines.
BALL_REF_MIN = 15.0    # taille de boulet ou phi = PHI_MAX (petit boulet).
BALL_REF_MAX = 80.0    # taille de boulet ou phi = PHI_MIN (gros boulet).



def effective_ball_size(x_um, distribution):
    """Taille de boulet EFFECTIVE qui casse une particule de taille x_um, car dans une charge
    distribuee ce sont les boulets bien adaptes a x qui la cassent majoritairement : ainsi on
    moyenne les tailles de boulets ponderees par leur contribution a la selection de x.
    taille_eff = somme_d [ contribution(d) * d ] / somme_d [ contribution(d) ]."""
    number_fracs = mass_to_number_fractions(distribution)
    contributions = {d: n * selection_by_ball(x_um, d) for d, n in number_fracs.items()}
    total = sum(contributions.values())
    if total <= 1e-12:
        # Aucun boulet ne casse cette taille : renvoie la taille moyenne de la charge.
        return sum(number_fracs.keys()) / len(number_fracs)
    return sum(c * d for d, c in contributions.items()) / total


def phi_for_ball(ball_size_mm):
    """phi (ponderation fines/gros de B) selon la taille de boulet effectif, car un gros boulet
    fracture en gros fragments (phi bas) et un petit boulet produit plus de fines (phi haut) :
    interpolation lineaire entre PHI_MAX (petit boulet) et PHI_MIN (gros boulet)."""
    frac = (ball_size_mm - BALL_REF_MIN) / (BALL_REF_MAX - BALL_REF_MIN)
    frac = max(0.0, min(1.0, frac))
    return PHI_MAX - frac * (PHI_MAX - PHI_MIN)


def breakage_cumulative_ball(x_i, x_j, phi):
    """Fonction de broyage cumulee avec un phi VARIABLE (dependant du boulet effectif), car la
    forme des fragments depend de la taille du boulet qui casse : ainsi B n'est plus normalisee."""
    if x_i >= x_j:
        return 1.0
    ratio = x_i / x_j
    return phi * ratio ** BRK_GAMMA + (1.0 - phi) * ratio ** BRK_BETA


def breakage_fraction_ball(i, j, sizes, distribution):
    """Fraction de masse de la classe j qui atterrit dans la classe i, avec la forme des
    fragments DEPENDANTE des boulets qui cassent la classe j : ainsi la distribution de boulets
    faconne la FORME de la PSD, pas seulement le P80."""
    if i <= j:
        return 0.0
    x_j = sizes[j]
    ball_eff = effective_ball_size(x_j, distribution)   # quel boulet casse la classe j
    phi = phi_for_ball(ball_eff)
    haut = sizes[i - 1] if i - 1 >= 0 else sizes[0]
    bas = sizes[i]
    return breakage_cumulative_ball(haut, x_j, phi) - breakage_cumulative_ball(bas, x_j, phi)

