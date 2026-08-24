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