"""
Classification hydraulique (hydrocyclone), car un cyclone ne trie pas par densite ni par
magnetisme mais par TAILLE : ainsi un flux entre et ressort en deux (overflow fin,
underflow grossier), chaque classe granulometrique etant partagee selon sa taille vs le
d50 de coupure. C'est le premier separateur qui exploite reellement la PSD.

Version initiale : partage par taille PURE (la mineralogie ne joue pas encore). Raffinements
prevus : effet de densite (les denses vont a l'underflow meme fins), apex et vortex finder.
"""
import numpy as np
from size_classes import class_representative_sizes, p80_from_psd, DEFAULT_GRID_UM


# Valeurs calees sur la correlation de Plitt (1976) : les exposants retrouvés par le module de
# calibration correspondent aux valeurs publiees (diametre 0.66, pression 0.28), car ta forme de
# modele est structurellement celle de Plitt : ainsi le cyclone est desormais fidele au standard.
# K = 13.27 cale a rho_s=2.65, CV=10% (absorbe le terme densite/CV de Plitt a ces conditions).
CYCLONE_K = 13.27       # echelle globale du d50 (Plitt : 11.93 * terme densite/CV)
CYCLONE_EXP_D = 0.66    # exposant du diametre (Plitt 1976)
CYCLONE_EXP_P = 0.28    # exposant de la pression (Plitt 1976)


def cyclone_cutpoint(diameter_cm, pressure_kpa, sharpness=3.0, pct_solids=50.0):
    """
    d50 de coupure (um) d'un hydrocyclone, car l'utilisateur regle un diametre et une
    pression, pas un d50 : ainsi une correlation simplifiee (type Plitt) donne d50 ~
    Dc^0.5 / P^0.25 -> gros cyclone coupe grossier, forte pression coupe fin.
    Le % solides decale le d50 (pulpe dense -> classification genee -> d50 plus grossier).
    Retour : (d50_um, sharpness).
    """
    dc = max(float(diameter_cm), 1.0)
    p = max(float(pressure_kpa), 1.0)
    # Correlation type Plitt avec constantes de module (calibrables) : gros cyclone coupe
    # grossier (exposant diametre), forte pression coupe fin (exposant pression negatif).
    d50 = CYCLONE_K * (dc ** CYCLONE_EXP_D) / (p ** CYCLONE_EXP_P)
    d50 *= solids_effect_cyclone(pct_solids)   # decalage du a la densite de pulpe
    return round(d50, 2), sharpness

def solids_effect_cyclone(pct_solids, reference=50.0, rho_s=2.65):
    """Effet du % solides sur le d50 d'un hydrocyclone, via le POLYNOME de Plitt (1976), car une
    pulpe dense gene la classification (viscosite -> le d50 grossit ; au-dela d'un seuil le
    cyclone rope et ne classe plus) : ainsi on reproduit la vraie forme de Plitt, non lineaire,
    qui s'incurve fortement a haute densite. Plitt travaille en concentration VOLUMIQUE CV ; on
    convertit donc le % solides massique via rho_s. Le facteur est NORMALISE a 1.0 a la reference
    (50% masse) et PLAFONNE a 3.0, car au-dela le polynome explose vers des valeurs absurdes
    (hors domaine de validite) alors que physiquement le cyclone est simplement bouche/rope.
    reference = % solides massique ou le d50 nominal s'applique."""
    def _cv(pct_mass):
        # Fraction volumique solide (%) a partir du % massique, car Plitt raisonne en volume :
        # v_solide / (v_solide + v_eau), avec rho_eau = 1.0.
        v_solide = pct_mass / rho_s
        v_eau = (100.0 - pct_mass) / 1.0
        return 100.0 * v_solide / (v_solide + v_eau)

    def _poly(cv):
        # Polynome exponentiel de Plitt (1976) : effet de la concentration volumique sur le d50.
        return np.exp(-0.301 + 0.0945 * cv - 0.00356 * cv ** 2 + 0.0000684 * cv ** 3)

    cv = _cv(pct_solids)
    cv_ref = _cv(reference)
    facteur = _poly(cv) / _poly(cv_ref)   # normalise a 1.0 a la reference
    # Plafond : au-dela, le cyclone rope (classification effondree), le polynome n'est plus valide.
    return float(min(facteur, 3.0))

def cyclone_partition(size_um, d50, sharpness):
    """Probabilite qu'une particule de taille donnee parte a l'UNDERFLOW (grossier), car la
    coupure n'est pas nette : ainsi P = x^k / (x^k + d50^k) (fines -> overflow, grosses ->
    underflow, transition autour du d50)."""
    x = max(float(size_um), 1e-6)
    return (x ** sharpness) / (x ** sharpness + d50 ** sharpness)


def classify_stream(stream, diameter_cm, pressure_kpa, grid=None,
                    sharpness=3.0, apply_p80_func=None, pct_solids=50.0):
    """
    Partage un flux en overflow (fin) + underflow (grossier) par classification en taille,
    car chaque classe granulometrique va majoritairement d'un cote selon sa taille : ainsi
    on partage la PSD classe par classe, on recalcule masse et PSD de chaque produit, et la
    mineralogie reste celle de l'alimentation (version taille pure).
    Retour : (overflow, underflow), deux Stream.
    """
    import copy
    if grid is None:
        grid = DEFAULT_GRID_UM
    if stream.psd_curve is None:
        raise ValueError("classify_stream exige une PSD sur le flux (psd_curve).")

    sizes = class_representative_sizes(grid)   # taille representative de chaque classe
    d50, sharp = cyclone_cutpoint(diameter_cm, pressure_kpa, sharpness, pct_solids=pct_solids)
    psd = stream.psd_curve

    # Pour chaque classe : fraction de sa masse qui part a l'underflow (le reste a l'overflow).
    p_under = [cyclone_partition(sizes[i], d50, sharp) for i in range(len(psd))]

    # Masse de chaque classe (t/h) = fraction PSD x masse totale.
    total_mass = stream.solids_tph
    class_mass = [psd[i] * total_mass for i in range(len(psd))]
    under_mass = [class_mass[i] * p_under[i] for i in range(len(psd))]
    over_mass = [class_mass[i] - under_mass[i] for i in range(len(psd))]

    mass_under = sum(under_mass)
    mass_over = sum(over_mass)

    def build(mass_by_class, total_out, name):
        s = copy.deepcopy(stream)
        s.name = f"{stream.name}_{name}"
        s.solids_tph = round(total_out, 4)
        if total_out > 1e-9:
            # PSD du produit = masses par classe renormalisees.
            new_psd = [round(m / total_out, 6) for m in mass_by_class]
            s.psd_curve = new_psd
            s.p80_um = round(p80_from_psd(grid, new_psd), 1)
        # Mineralogie et assays inchanges (version taille pure), car la taille ne trie pas
        # les mineraux entre eux ici : ainsi modal et teneurs restent ceux de l'alimentation.
        return s

    overflow = build(over_mass, mass_over, "overflow")
    underflow = build(under_mass, mass_under, "underflow")
    return overflow, underflow