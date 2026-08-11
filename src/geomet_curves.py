"""
geomet_curves.py
Indicateurs de performance et courbes geometallurgiques DERIVES du simulateur, car un
metallurgiste juge une separation par les recuperations et par la courbe teneur-recuperation :
ainsi on calcule, pour un concentre donne, la recuperation massique et la recuperation
metallurgique d'un metal, et l'on trace la courbe en balayant un reglage (separation simple
OU circuit), chaque point etant une simulation complete.

Les courbes SORTENT du modele physique : chaque point est une separation (ou un circuit)
re-calcule avec un reglage different.
"""

from separation import SeparationUnit, separate
from laws_gravity import gravity_recovery, gravity_cutpoint
from laws_magnetic import magnetic_recovery, magnetic_cutpoint
from laws_flotation import flotation_recovery, gold_flotation_recovery
from circuit_cu_zn import run_differential_circuit


# ---------------------------------------------------------------- indicateurs

def mass_recovery(feed, concentrate):
    """Recuperation massique (%), car c'est la part de la masse totale partie au concentre :
    ainsi masse_conc / masse_alim x 100."""
    if feed.solids_tph <= 1e-9:
        return 0.0
    return 100.0 * concentrate.solids_tph / feed.solids_tph


def metal_recovery(feed, concentrate, element):
    """Recuperation metallurgique (%) d'un metal, car c'est la part du metal partie au
    concentre : ainsi (teneur_conc x masse_conc) / (teneur_alim x masse_alim) x 100."""
    feed_metal = feed.assays.get(element, 0.0) * feed.solids_tph
    if feed_metal <= 1e-9:
        return 0.0
    conc_metal = concentrate.assays.get(element, 0.0) * concentrate.solids_tph
    return 100.0 * conc_metal / feed_metal


def performance_row(feed, stream, element):
    """Ligne de performance d'un produit, car on veut masse, recup massique, teneur et
    recup metallurgique d'un coup : ainsi on renvoie le tuple pret a afficher."""
    return {
        "masse_tph": round(stream.solids_tph, 2),
        "recup_massique_%": round(mass_recovery(feed, stream), 2),
        f"teneur_{element}_%": round(stream.assays.get(element, 0.0), 3),
        f"recup_metal_{element}_%": round(metal_recovery(feed, stream, element), 2),
    }


# ---------------------------------------------------------------- separation simple

def _apply_one(feed, unit_type, settings, prop_lookup=None, assay_func=None):
    """Applique une unite et renvoie (concentre, rejet), car chaque point de courbe est
    une separation : ainsi on aiguille vers la bonne loi selon la voie."""
    unit = SeparationUnit(unit_type, settings)
    if unit_type in ("shaking_table", "spiral", "falcon"):
        d50, ep = gravity_cutpoint(unit)
        reco = gravity_recovery(feed, d50, ep, densities=prop_lookup)
        return separate(feed, reco, assay_func=assay_func)
    elif unit_type == "magnetic":
        thr, sharp = magnetic_cutpoint(unit)
        reco = magnetic_recovery(feed, thr, sharp, mineral_props=prop_lookup)
        return separate(feed, reco, assay_func=assay_func)
    else:
        reco = flotation_recovery(feed, unit, mineral_props=prop_lookup)
        au = gold_flotation_recovery(feed, reco, unit)
        return separate(feed, reco, gold_recovery=au, assay_func=assay_func)


def grade_recovery_simple(feed, unit_type, base_settings, sweep_param, sweep_values,
                          element, prop_lookup=None, assay_func=None):
    """
    Courbe teneur-recuperation d'une separation simple, car on veut le compromis autour du
    point simule : ainsi on balaye sweep_param et l'on releve, pour chaque valeur, la
    recuperation metallurgique et la teneur du metal dans le concentre.
    Retour : liste de dicts {param, recup_metal_%, teneur_%, recup_massique_%}.
    """
    points = []
    for val in sweep_values:
        settings = dict(base_settings)
        settings[sweep_param] = val
        conc, _ = _apply_one(feed, unit_type, settings, prop_lookup, assay_func)
        points.append({
            "param": round(float(val), 3),
            "recup_metal_%": round(metal_recovery(feed, conc, element), 2),
            "teneur_%": round(conc.assays.get(element, 0.0), 3),
            "recup_massique_%": round(mass_recovery(feed, conc), 2),
        })
    # Tri par recuperation croissante, car une courbe teneur-recuperation se lit ainsi :
    # ainsi on evite les zigzags dus a un balayage non monotone.
    points.sort(key=lambda p: p["recup_metal_%"])
    return points


# ---------------------------------------------------------------- circuit

def grade_recovery_circuit(feed, stage_configs, stage_index, sweep_param, sweep_values,
                           element, target_conc_name, prop_lookup=None, assay_func=None):
    """
    Courbe teneur-recuperation d'un circuit, car un circuit a plusieurs concentres et
    plusieurs reglages : ainsi on balaye un parametre d'UN etage (stage_index) et l'on suit
    le metal dans UN concentre choisi (target_conc_name), en re-simulant tout le circuit a
    chaque point (car changer un etage affecte les suivants).
    Retour : liste de dicts {param, recup_metal_%, teneur_%, recup_massique_%}.
    """
    points = []
    for val in sweep_values:
        # Copie profonde des configs, car on ne modifie qu'un etage sans toucher l'original.
        configs = [dict(c) for c in stage_configs]
        configs[stage_index][sweep_param] = float(val)

        result = run_differential_circuit(feed, configs,
                                          prop_lookup=prop_lookup, assay_func=assay_func)
        conc = result["concentrates"].get(target_conc_name)
        if conc is None:
            continue
        points.append({
            "param": round(float(val), 3),
            "recup_metal_%": round(metal_recovery(feed, conc, element), 2),
            "teneur_%": round(conc.assays.get(element, 0.0), 3),
            "recup_massique_%": round(mass_recovery(feed, conc), 2),
        })
    # Tri par recuperation croissante, car une courbe teneur-recuperation se lit ainsi :
    # ainsi on evite les zigzags dus a un balayage non monotone.
    points.sort(key=lambda p: p["recup_metal_%"])
    return points


if __name__ == "__main__":
    import numpy as np
    from feed_generator import generate_feed

    print("=== Separation simple : indicateurs + courbe (Fe, magnetique) ===")
    feed = generate_feed("iron_flotation", n_samples=1, seed=1)[0]
    conc, rejet = _apply_one(feed, "magnetic", {"mode": "WHIMS_wet"})
    print("Concentre :", performance_row(feed, conc, "Fe"))
    print("Rejet     :", performance_row(feed, rejet, "Fe"))

    pts = grade_recovery_simple(feed, "magnetic", {"mode": "WHIMS_wet"},
                                "field_tesla", np.linspace(0.2, 1.5, 6), "Fe")
    print("\nCourbe (balayage champ) :")
    for p in pts:
        print(f"  champ={p['param']:.2f}  recup={p['recup_metal_%']:5.1f}%  "
              f"teneur={p['teneur_%']:.1f}%  masse={p['recup_massique_%']:.1f}%")

    print("\n=== Circuit Cu->Zn : courbe du Cu dans le concentre Cu (balayage pH etage Cu) ===")
    feed2 = generate_feed("polymetallic_refractory_au", n_samples=1, seed=3)[0]
    circuit = [
        {"name": "Cu", "pulp_ph": 9.0, "collector_gpt": 100, "depressed_minerals": ["sphalerite"]},
        {"name": "Zn", "pulp_ph": 10.5, "collector_gpt": 120, "activated_minerals": ["sphalerite"]},
    ]
    pts2 = grade_recovery_circuit(feed2, circuit, stage_index=0, sweep_param="pulp_ph",
                                  sweep_values=np.linspace(7.0, 11.0, 6),
                                  element="Cu", target_conc_name="Cu")
    for p in pts2:
        print(f"  pH={p['param']:.1f}  recup Cu={p['recup_metal_%']:5.1f}%  "
              f"teneur Cu={p['teneur_%']:.2f}%  masse={p['recup_massique_%']:.1f}%")