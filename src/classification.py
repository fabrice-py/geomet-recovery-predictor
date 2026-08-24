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
    # Constante calee pour des d50 realistes (quelques um a ~100 um).
    k_const = 45
    d50 = k_const * (dc ** 0.5) / (p ** 0.25)
    d50 *= solids_effect_cyclone(pct_solids)   # decalage du a la densite de pulpe
    return round(d50, 2), sharpness

def solids_effect_cyclone(pct_solids, reference=50.0):
    """Effet du % solides sur le d50 d'un hydrocyclone (phenomenologique), car une pulpe dense
    est plus visqueuse et gene la classification : ainsi le d50 AUGMENTE avec la densite de
    pulpe (les fines qui devraient partir en surverse sont retenues). Effet MONOTONE (decalage
    de coupure, pas un optimum), fidele a la correlation de Plitt qui inclut la concentration
    en solides. reference = % solides ou le d50 nominal s'applique."""
    ecart = pct_solids - reference
    return max(0.3, 1.0 + 0.020 * ecart)   # borne basse pour eviter un d50 absurde si tres dilue

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