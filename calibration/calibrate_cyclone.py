"""
Module de calibration de l'hydrocyclone contre la correlation de Plitt (1976).
Charge un jeu de d50 de reference (calcules par Plitt, le standard minieralurgique), fait
tourner le modele cyclone_cutpoint aux memes conditions, et cale les constantes CYCLONE_K,
CYCLONE_EXP_D, CYCLONE_EXP_P pour reproduire Plitt. Demonstration que l'infrastructure de
calibration s'applique a l'hydrocyclone : on doit voir l'exposant diametre converger vers
~0.66 et l'exposant pression vers ~0.28 (valeurs publiees de Plitt).
"""
import sys
import os
import csv
import numpy as np

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

import classification as cl


def charger_csv(chemin):
    """Charge un CSV en ignorant les lignes de commentaire (#), car les fichiers portent leur
    source en en-tete : ainsi la provenance reste dans le fichier."""
    with open(chemin, encoding="utf-8") as f:
        contenu = [l for l in f if not l.lstrip().startswith("#")]
    return list(csv.DictReader(contenu))


def _simuler_avec(donnees, k, exp_d, exp_p):
    """Fait tourner cyclone_cutpoint avec un jeu de constantes donne, en les posant
    temporairement dans le module, car l'optimiseur explore differentes valeurs : ainsi on
    sauvegarde/restaure. Renvoie la liste des ecarts relatifs (%). On appelle a pct_solids=50
    (reference de solids_effect_cyclone -> facteur 1) pour ISOLER diametre et pression, car le
    CSV Plitt est genere a CV fixe (l'effet %solides est traite a part)."""
    k0, d0, p0 = cl.CYCLONE_K, cl.CYCLONE_EXP_D, cl.CYCLONE_EXP_P
    try:
        cl.CYCLONE_K, cl.CYCLONE_EXP_D, cl.CYCLONE_EXP_P = k, exp_d, exp_p
        ecarts = []
        for row in donnees:
            dc = float(row["diameter_cm"])
            pr = float(row["pressure_kpa"])
            d50_ref = float(row["d50_um"])
            d50_mod, _ = cl.cyclone_cutpoint(dc, pr, pct_solids=50.0)
            ecarts.append((d50_mod - d50_ref) / d50_ref * 100.0)
        return ecarts
    finally:
        cl.CYCLONE_K, cl.CYCLONE_EXP_D, cl.CYCLONE_EXP_P = k0, d0, p0


def _rmse(ecarts):
    return float(np.sqrt(np.mean([e ** 2 for e in ecarts])))


def calibrer(chemin_csv):
    """Cale CYCLONE_K, CYCLONE_EXP_D, CYCLONE_EXP_P contre les d50 de Plitt, via evolution
    differentielle. Affiche RMSE et exposants avant/apres : on veut voir EXP_D -> ~0.66 et
    EXP_P -> ~0.28 (valeurs de Plitt)."""
    from scipy.optimize import differential_evolution
    donnees = charger_csv(chemin_csv)

    x0 = [cl.CYCLONE_K, cl.CYCLONE_EXP_D, cl.CYCLONE_EXP_P]
    rmse_depart = _rmse(_simuler_avec(donnees, *x0))

    def cout(params):
        return _rmse(_simuler_avec(donnees, *params))

    # Bornes : K (5-30, echelle Plitt plus basse que 45), exp_D (0.3-1.0), exp_P (0.1-0.5).
    bornes = [(5.0, 30.0), (0.3, 1.0), (0.1, 0.5)]
    res = differential_evolution(cout, bornes, maxiter=40, popsize=15, seed=42,
                                 tol=0.01, polish=True)
    k_o, d_o, p_o = res.x

    print("=== CALIBRATION HYDROCYCLONE (reference Plitt 1976) ===")
    print(f"Points : {len(donnees)} (diametres x pressions, rho_s=2.65, CV=10%)")
    print(f"RMSE avant : {rmse_depart:.1f}%")
    print(f"RMSE apres : {res.fun:.1f}%")
    print()
    print("Constantes calees :")
    print(f"  CYCLONE_K     : {k_o:.2f}   (depart {x0[0]})")
    print(f"  CYCLONE_EXP_D : {d_o:.3f}   (depart {x0[1]} ; Plitt publie 0.66)")
    print(f"  CYCLONE_EXP_P : {p_o:.3f}   (depart {x0[2]} ; Plitt publie 0.28)")
    print()
    print("NB IMPORTANT sur le RMSE ~0% : il est ATTENDU ici et ne signale PAS un surajustement.")
    print("  Le modele (K*Dc^a/P^b) et Plitt ont la MEME structure algebrique ; a rho_s et CV")
    print("  fixes, le terme densite/CV de Plitt devient une constante absorbee par K. Le calage")
    print("  est donc un ajustement algebrique EXACT, pas un fit sur donnees bruitees (comparer")
    print("  au broyage : calage sur mesures reelles -> RMSE 27-30%, residu irreductible normal).")
    print("  Ce resultat PROUVE que la forme du modele reproduit Plitt et que l'infra converge,")
    print("  mais ne VALIDE PAS le modele contre des mesures reelles (Plitt lui-meme a +/-20-30%")
    print("  d'ecart avec l'experience). Distinction : 'reproduit la correlation' != 'predit le reel'.")
    return {"CYCLONE_K": k_o, "CYCLONE_EXP_D": d_o, "CYCLONE_EXP_P": p_o}


if __name__ == "__main__":
    chemin = os.path.join(_RACINE, "calibration", "data",
                          "hydrocyclone_plitt_reference.csv")
    calibrer(chemin)