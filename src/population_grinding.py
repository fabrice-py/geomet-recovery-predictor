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
            frac = breakage_fraction(k, i, sizes)
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
    # 2) Appliquer ce meme nombre de pas avec la charge REELLE.
    current = list(psd)
    for _ in range(n_steps):
        current = grinding_step(current, sizes, distribution, delta)
    return current, round(p80_from_psd(grid, current), 1), n_steps