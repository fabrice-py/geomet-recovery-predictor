"""
Module de calibration du broyage par bilan de population (brique 1).
Charge un jeu de donnees observees (x50 mesures selon temps et taille de boulet),
fait tourner le modele de broyage aux memes conditions, et affiche l'ecart de depart
entre le P50 predit et le x50 mesure. L'optimiseur (ajustement des constantes) viendra
en brique 2.
"""
import sys
import os
import csv
import numpy as np

# On rend le paquet src importable, car le module de calibration vit dans calibration/
# et doit atteindre le coeur du simulateur : ainsi on ajoute src/ au chemin.
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RACINE, "src"))

from size_classes import DEFAULT_GRID_UM, make_psd_rosin_rammler, class_representative_sizes
import population_grinding as pg


def p50_from_psd(grid, psd):
    """P50 (mediane) interpole depuis la PSD, car la calibration compare le modele au x50
    mesure : ainsi on lit la taille au passant cumule de 50%. Meme logique que p80_from_psd
    mais avec la cible 0.50 au lieu de 0.80."""
    # psd est la fraction massique par classe (fin -> grossier ou l'inverse selon convention) ;
    # on reconstruit le passant cumule et on interpole a 50%.
    sizes = class_representative_sizes(grid)
    # Passant cumule : fraction de masse PLUS FINE que la borne haute de chaque classe.
    # On trie par taille croissante pour une interpolation propre.
    paires = sorted(zip(sizes, psd))
    xs = [p[0] for p in paires]
    fracs = [p[1] for p in paires]
    cumul = np.cumsum(fracs)  # passant croissant avec la taille
    cible = 0.50 * cumul[-1]
    # Interpolation lineaire pour trouver la taille au passant = 50%.
    for i in range(len(cumul)):
        if cumul[i] >= cible:
            if i == 0:
                return xs[0]
            # interpolation entre i-1 et i
            f0, f1 = cumul[i - 1], cumul[i]
            x0, x1 = xs[i - 1], xs[i]
            if f1 == f0:
                return x1
            return x0 + (x1 - x0) * (cible - f0) / (f1 - f0)
    return xs[-1]


def charger_csv(chemin):
    """Charge un CSV de donnees en ignorant les lignes de commentaire (#), car les fichiers
    portent leur source en en-tete : ainsi la provenance reste dans le fichier sans gener
    la lecture. Renvoie une liste de dicts."""
    lignes = []
    with open(chemin, encoding="utf-8") as f:
        contenu = [l for l in f if not l.lstrip().startswith("#")]
    lecteur = csv.DictReader(contenu)
    for row in lecteur:
        lignes.append(row)
    return lignes


def simuler_x50(temps_min, boulet_mm, k_temps, f80_um=3350.0):
    """Fait tourner le modele de broyage pour un temps et une taille de boulet donnes, et
    renvoie le P50 predit. Le temps est converti en nombre de pas via k_temps (pas/min), car
    le modele raisonne en pas discrets : ainsi on relie l'echelle physique (min) au modele."""
    grid = DEFAULT_GRID_UM
    sizes = class_representative_sizes(grid)
    psd = make_psd_rosin_rammler(grid, f80_um)
    distribution = {float(boulet_mm): 1.0}  # charge mono-taille (le jeu coke fixe une taille)
    nb_pas = max(1, int(round(temps_min * k_temps)))
    for _ in range(nb_pas):
        psd = pg.grinding_step(psd, sizes, distribution, delta=0.05)
    return p50_from_psd(grid, psd)


def evaluer_depart(chemin_csv, k_temps=20.0):
    """Affiche l'ecart de depart (avant calibration) entre P50 predit et x50 mesure, pour
    chaque point du jeu de donnees. Sert de reference : la brique 2 cherchera a reduire cet
    ecart en ajustant les constantes."""
    donnees = charger_csv(chemin_csv)
    print(f"{'temps':>6} {'boulet':>7} {'x50_mes':>9} {'P50_mod':>9} {'ecart%':>8}")
    print("-" * 44)
    ecarts = []
    for row in donnees:
        t = float(row["temps_min"])
        b = float(row["taille_boulet_mm"])
        x50_mes = float(row["x50_mesure_um"])
        p50_mod = simuler_x50(t, b, k_temps)
        ecart = 100.0 * (p50_mod - x50_mes) / x50_mes
        ecarts.append(ecart)
        print(f"{t:>6.1f} {b:>7.1f} {x50_mes:>9.0f} {p50_mod:>9.0f} {ecart:>+8.1f}")
    rmse = float(np.sqrt(np.mean([(e) ** 2 for e in ecarts])))
    print("-" * 44)
    print(f"Ecart quadratique moyen (RMSE relatif) : {rmse:.1f}%")
    print(f"k_temps utilise : {k_temps} pas/min")


def _simuler_avec_params(donnees, k_temps, sel_alpha, sel_k_mu):
    """Refait tourner les 24 simulations avec un jeu de constantes donne, en modifiant
    TEMPORAIREMENT les globales du module de broyage, car l'optimiseur doit explorer
    differentes valeurs : ainsi on sauvegarde puis restaure les valeurs d'origine pour ne
    pas polluer le module. Renvoie la liste des ecarts relatifs."""
    # Sauvegarde des valeurs d'origine.
    alpha_0, kmu_0 = pg.SEL_ALPHA, pg.SEL_K_MU
    try:
        pg.SEL_ALPHA = sel_alpha
        pg.SEL_K_MU = sel_k_mu
        ecarts = []
        for row in donnees:
            t = float(row["temps_min"])
            b = float(row["taille_boulet_mm"])
            x50_mes = float(row["x50_mesure_um"])
            p50_mod = simuler_x50(t, b, k_temps)
            ecarts.append(100.0 * (p50_mod - x50_mes) / x50_mes)
        return ecarts
    finally:
        # Restauration systematique, meme en cas d'erreur, car laisser des globales modifiees
        # fausserait tout appel ulterieur au modele.
        pg.SEL_ALPHA, pg.SEL_K_MU = alpha_0, kmu_0


def _rmse(ecarts):
    """Ecart quadratique moyen relatif (%), la grandeur que l'optimiseur minimise."""
    return float(np.sqrt(np.mean([e ** 2 for e in ecarts])))


def calibrer(chemin_csv):
    """Ajuste (k_temps, SEL_ALPHA, SEL_K_MU) pour minimiser le RMSE entre P50 predit et x50
    mesure, via scipy. Affiche le RMSE et les parametres avant/apres, car la calibration doit
    prouver qu'elle reduit reellement l'ecart : ainsi on voit l'amelioration chiffree."""
    from scipy.optimize import differential_evolution
    donnees = charger_csv(chemin_csv)

    # Valeurs de depart : k_temps arbitraire + constantes actuelles du module.
    x0 = [20.0, pg.SEL_ALPHA, pg.SEL_K_MU]
    bornes = [(1.0, 50.0), (0.5, 2.0), (0.02, 0.15)]

    rmse_depart = _rmse(_simuler_avec_params(donnees, *x0))

    def cout(params):
        k_temps, sel_alpha, sel_k_mu = params
        return _rmse(_simuler_avec_params(donnees, k_temps, sel_alpha, sel_k_mu))

    # differential_evolution : optimiseur GLOBAL par population, sans gradient, car le cout
    # est discontinu (le nombre de pas = round(temps x k_temps) casse la derivee sur k_temps) :
    # ainsi L-BFGS-B laissait k_temps fige (gradient nul par l'arrondi), tandis que l'evolution
    # differentielle explore l'espace entier sans buter sur ce probleme.
    res = differential_evolution(cout, bornes, maxiter=30, popsize=12, seed=42,
                                 tol=0.01, polish=False)

    k_opt, alpha_opt, kmu_opt = res.x
    rmse_final = res.fun

    print("=== CALIBRATION BROYAGE (jeu coke 2021) ===")
    print(f"RMSE avant : {rmse_depart:.1f}%")
    print(f"RMSE apres : {rmse_final:.1f}%")
    print()
    print("Parametres cales :")
    print(f"  k_temps   (pas/min) : {k_opt:.2f}   (depart 20.0)")
    print(f"  SEL_ALPHA           : {alpha_opt:.3f}   (depart {x0[1]:.3f})")
    print(f"  SEL_K_MU            : {kmu_opt:.4f}   (depart {x0[2]:.4f})")
    print()
    print("NB : calage sur coke (voie seche, Jb/U fixes) = test d'infrastructure, non une")
    print("     calibration de production pour un minerai donne.")
    return {"k_temps": k_opt, "SEL_ALPHA": alpha_opt, "SEL_K_MU": kmu_opt,
            "rmse_avant": rmse_depart, "rmse_apres": rmse_final}

def comparer_params_publies(chemin_csv):
    """Compare les constantes du modele aux parametres de selection PUBLIES (Petrakis 2017),
    car ces valeurs sont des cibles de reference issues d'essais reels : ainsi on valide que la
    STRUCTURE du modele (SEL_ALPHA, SEL_LAMBDA, SEL_K_MU) reproduit des ordres de grandeur
    documentes, pour plusieurs materiaux. Mode different du calage coke (pas de simulation ici,
    comparaison directe de parametres)."""
    donnees = charger_csv(chemin_csv)
    print("=== COMPARAISON AUX PARAMETRES PUBLIES (Petrakis 2017) ===")
    print("Correspondance : SEL_ALPHA<->alpha, SEL_LAMBDA<->Lambda, SEL_K_MU = mu_mm / d_mm")
    print()
    print(f"{'materiau':>9} {'U%':>4} {'alpha':>7} {'Lambda':>7} {'mu_mm':>7} "
          f"{'SEL_K_MU_impl':>13}")
    print("-" * 56)
    for row in donnees:
        mat = row["materiau"]
        u = float(row["U_pct"])
        alpha = float(row["alpha"])
        lam = float(row["Lambda"])
        mu_mm = float(row["mu_mm"])
        boulet_mm = float(row["boulet_mm"])
        # SEL_K_MU implique par ces donnees : mu_mm = SEL_K_MU * d_mm, donc SEL_K_MU = mu/d.
        sel_k_mu_impl = mu_mm / boulet_mm
        print(f"{mat:>9} {u:>4.0f} {alpha:>7.3f} {lam:>7.3f} {mu_mm:>7.2f} "
              f"{sel_k_mu_impl:>13.4f}")
    print("-" * 56)
    print(f"Valeurs actuelles du modele : SEL_ALPHA={pg.SEL_ALPHA}, "
          f"SEL_LAMBDA={pg.SEL_LAMBDA}, SEL_K_MU={pg.SEL_K_MU}")
    print()
    print("Lecture : alpha et Lambda se comparent directement aux constantes du modele ;")
    print("SEL_K_MU_impl est la valeur qui reproduirait le mu publie pour ce couple materiau/U.")

if __name__ == "__main__":
    chemin = os.path.join(_RACINE, "calibration", "data", "grinding_coke_2021.csv")
    print("--- Ecart de depart (avant calibration) ---")
    evaluer_depart(chemin)
    print()
    calibrer(chemin)
    print()
    chemin_petrakis = os.path.join(_RACINE, "calibration", "data",
                                   "selection_params_2017.csv")
    comparer_params_publies(chemin_petrakis)