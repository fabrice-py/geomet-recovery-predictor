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

def filling_effect_grinding(filling_pct, optimum=37.0):
    """Effet du taux de remplissage en BOULETS (Jb) sur le broyage (phenomenologique), car la
    charge de corps broyants determine le nombre et la violence des impacts DISPONIBLES :
    - trop peu (< optimum) : peu de boulets, peu d'impacts -> energie de broyage faible.
    - trop plein (> optimum) : les boulets se genent, la cascade est etouffee.
    Cloche autour de ~37%. Retour : facteur d'efficacite (<= 1) sur l'energie disponible."""
    ecart = abs(filling_pct - optimum)
    return max(0.5, 1.0 - 0.012 * ecart)


def interstitial_effect_grinding(comblement_u, optimum=1.0):
    """Effet du comblement interstitiel (U = volume de pulpe / volume des vides entre boulets)
    sur le TRANSFERT de l'energie au minerai (phenomenologique) :
    - U < optimum : vides mal remplis -> les boulets frappent dans le vide ou entre eux,
      l'energie n'atteint pas le minerai (gaspillage, usure).
    - U > optimum : charge noyee -> la pulpe deborde et amortit les impacts (boulets qui
      'flottent').
    Optimum ~1.0 (vides juste combles). Retour : facteur d'efficacite (<= 1) sur l'energie
    reellement transmise au minerai. Distinct de Jb (energie disponible) et du % solides
    (rheologie) : ainsi les trois causes se cumulent sans doublon."""
    ecart = abs(comblement_u - optimum)
    return max(0.4, 1.0 - 0.40 * ecart)   # sensible : U s'ecarte sur une plage etroite (0.5-1.5)

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
                 pct_solids=75.0, mode="humide", filling_pct=37.0, comblement_u=1.0,
                 modele="bond", ball_distribution=None):
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
    # Efficacite globale du broyage = produit de TROIS facteurs independants, car chacun agit
    # sur un maillon distinct de la chaine energetique (pas de doublon) :
    #   - Jb (remplissage en boulets)  -> energie DISPONIBLE (nombre/violence des impacts) ;
    #   - U  (comblement interstitiel) -> TRANSFERT de cette energie au minerai ;
    #   - % solides (densite de pulpe) -> RHEOLOGIE (amortissement/dispersion).
    # Ainsi une conduite mal reglee sur plusieurs leviers cumule les pertes.
    eff = (solids_effect_grinding(pct_solids, mode)
           * filling_effect_grinding(filling_pct)
           * interstitial_effect_grinding(comblement_u))
    energy_effective = energy_kwht * eff
    # P80 de reference par la loi de Bond (energie effective) : c'est l'ancre energetique.
    p80_bond = bond_product_p80(f80, work_index, energy_effective)

    if modele == "population" and stream.psd_curve is not None:
        # Modele par bilan de population : Bond cale l'energie (via p80_bond), la DISTRIBUTION
        # DE BOULETS faconne la forme de la PSD. Ainsi deux charges a energie egale donnent des
        # granulometries differentes (efficacite ET forme).
        from population_grinding import grind_psd_energy_based, DEFAULT_BALL_DISTRIBUTION
        from size_classes import class_representative_sizes
        dist = ball_distribution if ball_distribution else DEFAULT_BALL_DISTRIBUTION
        sizes = class_representative_sizes(grid)
        psd_out, p80_pop, _ = grind_psd_energy_based(
            stream.psd_curve, sizes, grid, dist, p80_bond)
        stream.psd_curve = psd_out
        stream.p80_um = p80_pop
        # Recalcule la liberation sur le P80 obtenu, sans reconstruire la PSD (deja faconnee).
        if apply_p80_func is not None:
            saved = list(stream.psd_curve)
            apply_p80_func(stream, p80_pop, grid=grid)
            stream.psd_curve = saved   # on re-impose la PSD du bilan de population
            stream.p80_um = p80_pop
        return stream

    # Modele Bond (simple) : P80 -> PSD Rosin-Rammler (comportement de reference).
    if apply_p80_func is not None:
        apply_p80_func(stream, p80_bond, grid=grid)
    else:
        stream.psd_curve = make_psd_rosin_rammler(grid, p80_bond, m=1.0)
        stream.p80_um = round(p80_from_psd(grid, stream.psd_curve), 1)
    return stream