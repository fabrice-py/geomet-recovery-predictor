"""
Broyage (loi de Bond), car un broyeur ne separe pas mais TRANSFORME le flux : ainsi un
flux entre et ressort plus fin (P80 reduit) et mieux libere, sans changer sa masse ni sa
mineralogie globale. La loi de Bond relie l'energie specifique (kWh/t) a la reduction de
taille, ponderee par la durete du minerai (indice de travail Wi).
"""
import numpy as np
from size_classes import make_psd_rosin_rammler, p80_from_psd, DEFAULT_GRID_UM

def solids_effect_grinding(pct_solids, mode, optimum=75.0):
    """Effet du % solides sur le broyage HUMIDE (phenomenologique), car la densite de pulpe
    conditionne le transfert d'energie des boulets aux particules :
    - trop dense (> optimum) : la pulpe amortit les impacts (les boulets 'pataugent').
    - trop dilue (< optimum) : moins de particules entre boulet et blindage (contacts perdus).
    Hors optimum, l'energie UTILE au broyage baisse -> moins de reduction de P80.
    Ne s'applique qu'en voie humide : en sec, pas de pulpe (facteur 1).
    Retour : facteur d'efficacite energetique (<= 1) qui module l'energie specifique."""
    if mode != "humide":
        return 1.0
    ecart = abs(pct_solids - optimum)
    return max(0.5, 1.0 - 0.010 * ecart)

def bond_product_p80(f80, work_index, energy_kwht):
    """
    P80 de sortie (um) d'un broyage, car la loi de Bond donne l'energie pour une reduction :
    ainsi on l'inverse pour trouver la finesse atteinte avec l'energie appliquee.
    W = 10 * Wi * (1/sqrt(P80) - 1/sqrt(F80))  ->  P80 = 1 / (W/(10 Wi) + 1/sqrt(F80))^2
    """
    f80 = max(float(f80), 1.0)
    wi = max(float(work_index), 1.0)
    w = max(float(energy_kwht), 0.0)
    inv_sqrt_p80 = w / (10.0 * wi) + 1.0 / np.sqrt(f80)
    p80 = 1.0 / (inv_sqrt_p80 ** 2)
    # On ne "grossit" jamais : un broyeur ne peut que reduire (securite numerique).
    return round(min(p80, f80), 2)


def grind_stream(stream, work_index, energy_kwht, grid=None, apply_p80_func=None,
                 pct_solids=75.0, mode="humide"):
    """
    Applique un broyage a un flux (en place), car le broyeur transforme la PSD et la
    liberation sans toucher a la masse ni a la mineralogie : ainsi on calcule le P80 de
    sortie (Bond), on reconstruit la PSD, puis on recalcule la liberation via apply_p80.
    apply_p80_func : la fonction apply_p80 (injectee pour eviter un import circulaire).
    Retour : le flux modifie (P80 reduit, PSD plus fine, liberation amelioree).
    """
    if grid is None:
        grid = DEFAULT_GRID_UM
    # F80 d'entree : lu depuis la PSD si presente, sinon depuis p80_um.
    if stream.psd_curve is not None:
        f80 = p80_from_psd(grid, stream.psd_curve)
    else:
        f80 = stream.p80_um
    # Effet du % solides : une pulpe hors optimum reduit l'energie UTILE au broyage, car elle
    # amortit les impacts (dense) ou disperse les contacts (dilue) : ainsi on module l'energie
    # specifique par un facteur d'efficacite avant d'appliquer la loi de Bond.
    eff = solids_effect_grinding(pct_solids, mode)
    energy_effective = energy_kwht * eff
    # P80 de sortie par la loi de Bond, avec l'energie effective.
    p80_out = bond_product_p80(f80, work_index, energy_effective)
    # Reconstruction PSD + liberation via apply_p80 (qui refait PSD et cascade de liberation).
    if apply_p80_func is not None:
        apply_p80_func(stream, p80_out, grid=grid)
    else:
        stream.psd_curve = make_psd_rosin_rammler(grid, p80_out, m=1.0)
        stream.p80_um = round(p80_from_psd(grid, stream.psd_curve), 1)
    return stream