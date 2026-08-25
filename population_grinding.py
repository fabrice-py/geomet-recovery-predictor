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