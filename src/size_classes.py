"""
Grille granulometrique commune au flowsheet et outils de manipulation des PSD, car un
broyeur et un hydrocyclone raisonnent sur la TAILLE des particules : ainsi on represente
chaque flux par une distribution massique sur une grille de classes partagee.

La grille est une liste de bornes de tamis DECROISSANTES (um). n bornes -> n classes :
la classe 0 est "au-dessus de la 1re borne" (refus), les suivantes sont des intervalles
[borne_i+1, borne_i], la derniere est "sous la derniere borne" (passant fin).
"""
import numpy as np

# Grille par defaut (serie de tamis en um, decroissante), car il faut un point de depart :
# ainsi le flowsheet a une granulometrie commune que l'utilisateur pourra redefinir.
DEFAULT_GRID_UM = [3350.0, 2360.0, 1700.0, 1180.0, 850.0, 600.0, 425.0,
                   300.0, 212.0, 150.0, 106.0, 75.0, 53.0, 38.0, 25.0, 15.0]


def class_labels(grid):
    """Libelles lisibles des classes definies par une grille, car l'affichage doit nommer
    chaque intervalle : ainsi on produit '+300', '212-300', ..., '-15' (en um)."""
    labels = [f"+{grid[0]:.0f}"]
    for i in range(len(grid) - 1):
        labels.append(f"{grid[i+1]:.0f}-{grid[i]:.0f}")
    labels.append(f"-{grid[-1]:.0f}")
    return labels


def class_representative_sizes(grid):
    """Taille representative de chaque classe (um), car les lois (partage cyclone, P80) ont
    besoin d'une taille par classe : ainsi on prend la moyenne geometrique des bornes, et
    des tailles extrapolees pour la classe grossiere et la classe fine (ouvertes)."""
    sizes = []
    # Classe grossiere (au-dessus de grid[0]) : on l'estime un cran au-dessus.
    sizes.append(grid[0] * 1.5)
    for i in range(len(grid) - 1):
        sizes.append(float(np.sqrt(grid[i] * grid[i + 1])))   # moyenne geometrique
    # Classe fine (sous grid[-1]) : on l'estime un cran en dessous.
    sizes.append(grid[-1] * 0.5)
    return sizes


def make_psd_rosin_rammler(grid, p80, m=1.0):
    """
    Construit une PSD (fractions massiques par classe) suivant une loi de Rosin-Rammler de
    P80 vise, car il faut une distribution initiale coherente avec le broyage : ainsi la
    fraction passante a la taille x vaut 1 - exp(-(x/x0)^m), x0 etant cale pour que 80% de
    la masse passe a p80.
    Retour : liste de fractions (somme = 1), une par classe (meme ordre que class_labels).
    """
    # Calage de x0 pour que passant(p80) = 0.80, car par definition du P80 : ainsi
    # 0.80 = 1 - exp(-(p80/x0)^m) -> x0 = p80 / (-ln(0.20))^(1/m).
    x0 = p80 / ((-np.log(0.20)) ** (1.0 / m))

    def passing(x):
        return 1.0 - np.exp(-((x / x0) ** m))

    # Passant cumule a chaque borne (de la plus grande a la plus petite).
    # frac de la classe = passant(borne_haute) - passant(borne_basse).
    n_classes = len(grid) + 1
    fracs = [0.0] * n_classes
    # Classe 0 : refus au-dessus de grid[0] -> 1 - passant(grid[0]).
    fracs[0] = 1.0 - passing(grid[0])
    # Classes intermediaires : entre deux bornes.
    for i in range(len(grid) - 1):
        fracs[i + 1] = passing(grid[i]) - passing(grid[i + 1])
    # Derniere classe : passant sous grid[-1].
    fracs[-1] = passing(grid[-1])
    # Normalisation (securite numerique).
    total = sum(fracs)
    if total > 1e-12:
        fracs = [f / total for f in fracs]
    return [round(f, 6) for f in fracs]


def p80_from_psd(grid, psd):
    """
    Calcule le P80 (um) a partir d'une PSD sur une grille, car le P80 est desormais DERIVE
    de la distribution : ainsi on interpole sur la courbe de passant cumule la taille sous
    laquelle passent 80% de la masse.
    """
    # Passant cumule aux bornes, de la plus fine a la plus grossiere.
    # On construit des points (taille_borne, passant_cumule_sous_cette_borne).
    # psd[0] = refus (+grid[0]), psd[-1] = passant fin (-grid[-1]).
    # Passant sous grid[k] = somme des classes plus fines que grid[k].
    n = len(grid)
    # cumulative passing sous chaque borne grid[i]
    points = []  # (taille, passant)
    for i in range(n):
        # passant sous grid[i] = somme des fractions des classes d'indice > i
        passing_i = sum(psd[i + 1:])   # classes plus fines que la borne grid[i]
        points.append((grid[i], passing_i))
    # Ajoute le point fin (taille -> 0, passant -> 0 au plus fin extrapole) et grossier.
    # points est dans l'ordre des bornes decroissantes ; trions par taille croissante.
    points = sorted(points, key=lambda p: p[0])
    sizes = [p[0] for p in points]
    passings = [p[1] for p in points]
    # Interpolation lineaire pour trouver la taille ou passant = 0.80.
    target = 0.80
    if passings[-1] <= target:
        return round(sizes[-1], 1)      # tout est fin : P80 au-dela de la borne max
    if passings[0] >= target:
        return round(sizes[0], 1)       # deja 80% sous la plus petite borne
    for i in range(len(sizes) - 1):
        if passings[i] <= target <= passings[i + 1]:
            # interpolation lineaire
            frac = (target - passings[i]) / (passings[i + 1] - passings[i])
            return round(sizes[i] + frac * (sizes[i + 1] - sizes[i]), 1)
    return round(sizes[-1], 1)