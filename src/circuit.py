"""
circuit.py
Chaînage d'unités de séparation en série, car une usine enchaîne les opérations : ainsi
le rejet d'une unité alimente la suivante, et l'on collecte tous les concentrés produits.

Le chaînage reste générique, car il ne connaît pas la physique : ainsi une fonction
d'aiguillage appelle la bonne loi selon le type d'unité, et la cascade se contente de
faire circuler les flux.
"""

from separation import separate
from laws_gravity import gravity_recovery, gravity_cutpoint, gold_gravity_recovery
from laws_magnetic import magnetic_recovery, magnetic_cutpoint
from laws_flotation import flotation_recovery, gold_flotation_recovery
from comminution import grind_stream
from classification import classify_stream

def apply_unit(stream, unit, conc_name="concentre", tail_name="rejet",  prop_lookup=None, assay_func=None):
    """
    Application d'une unité à un flux, car chaque voie a sa propre loi : ainsi on aiguille
    vers la bonne physique selon le type d'unité, puis on partage le flux en conséquence.
    """
    if unit.unit_type in ("shaking_table", "spiral", "falcon"):
        d50, ep = gravity_cutpoint(unit)
        reco = gravity_recovery(stream, d50, ep, densities=prop_lookup)
        au = gold_gravity_recovery(stream, reco, unit, d50=d50, ep=ep)
        return separate(stream, reco, gold_recovery=au, conc_name=conc_name, tail_name=tail_name, assay_func=assay_func)

    elif unit.unit_type == "magnetic":
        thr, sharp = magnetic_cutpoint(unit)
        reco = magnetic_recovery(stream, thr, sharp, mineral_props=prop_lookup,
                                 pct_solids=unit.settings.get("pct_solids", 35.0),
                                 mode=unit.settings.get("mode", "WHIMS_wet"))
        return separate(stream, reco, conc_name=conc_name, tail_name=tail_name,
                        assay_func=assay_func)

    elif unit.unit_type == "flotation":
        reco = flotation_recovery(stream, unit, mineral_props=prop_lookup)
        au_reco = gold_flotation_recovery(stream, reco, unit)
        return separate(stream, reco, gold_recovery=au_reco,
                        conc_name=conc_name, tail_name=tail_name, assay_func=assay_func)

    else:
        raise ValueError(f"Type d'unité inconnu : {unit.unit_type}")


def run_series(feed, stages, prop_lookup=None, assay_func=None,
               grid=None, apply_p80_func=None):
    """
    Application d'une cascade d'unites en serie, car le rejet de chaque etage alimente le
    suivant : ainsi on collecte un concentre par etage et un unique rejet final.
    stages : liste de tuples (nom_etage, SeparationUnit).
    Un etage de type 'ball_mill' TRANSFORME le flux (broyage) au lieu de le separer : il ne
    produit pas de concentre, il affine le flux qui continue vers l'etage suivant.
    grid, apply_p80_func : requis pour le broyage (reconstruction PSD + liberation).
    Retour : dict avec les concentres par etage, le rejet final, les flux d'entree, et la
    liste des etages de broyage (pour l'affichage).
    """
    concentrates = {}
    stage_feeds = {}
    mill_outputs = {}           # flux de sortie des broyeurs, car ils ne font pas de concentre
    cyclone_outputs = {}
    current = feed
    for stage_name, unit in stages:
        stage_feeds[stage_name] = current
        if unit.unit_type == "ball_mill":
            s = unit.settings
            import copy
            ground = copy.deepcopy(current)
            grind_stream(ground, work_index=s.get("work_index", 15.0),
                         energy_kwht=s.get("energy_kwht", 10.0),
                         grid=grid, apply_p80_func=apply_p80_func,
                                                  pct_solids=s.get("pct_solids", 75.0),
                         mode=s.get("mode", "humide"),
                         filling_pct=s.get("filling_pct", 37.0),
                         comblement_u=s.get("comblement_u", 1.0))
            mill_outputs[stage_name] = ground
            current = ground
        elif unit.unit_type == "hydrocyclone":
            # Classification par taille : deux flux (overflow fin, underflow grossier).
            # L'utilisateur choisit lequel CONTINUE ; l'autre est un produit de sortie.
            s = unit.settings
            over, under = classify_stream(
                current, diameter_cm=s.get("diameter_cm", 15.0),
                pressure_kpa=s.get("pressure_kpa", 100.0), grid=grid,
                apply_p80_func=apply_p80_func, pct_solids=s.get("pct_solids", 50.0))
            cyclone_outputs[stage_name] = {"overflow": over, "underflow": under}
            if s.get("continue_flux", "overflow") == "underflow":
                current = under
                concentrates[f"{stage_name}_overflow"] = over   # produit de sortie
            else:
                current = over
                concentrates[f"{stage_name}_underflow"] = under  # produit de sortie
        else:
            conc, tail = apply_unit(current, unit,
                                    conc_name=f"conc_{stage_name}",
                                    tail_name=f"rejet_{stage_name}",
                                    prop_lookup=prop_lookup, assay_func=assay_func)
            concentrates[stage_name] = conc
            current = tail         # le rejet devient l'alimentation de l'étage suivant
    return {"feed": feed, "concentrates": concentrates, "final_tail": current,
            "stage_feeds": stage_feeds, "mill_outputs": mill_outputs,
            "cyclone_outputs": cyclone_outputs}


def mass_check(result):
    """
    Vérification de la conservation de la masse sur tout le circuit, car un bilan doit
    toujours boucler : ainsi la somme des concentrés + le rejet final doit égaler
    l'alimentation, à l'arrondi près.
    """
    conc_total = sum(c.solids_tph for c in result["concentrates"].values())
    tail = result["final_tail"].solids_tph
    feed = result["feed"].solids_tph
    return conc_total, tail, feed, round(conc_total + tail, 4)


if __name__ == "__main__":
    # Test : une cascade de trois cellules de flottation identiques (rougher), car on veut
    # voir la récupération cumulée monter d'étage en étage et la masse boucler.
    from feed_generator import generate_feed
    from separation import SeparationUnit

    feed = generate_feed("polymetallic_refractory_au", n_samples=1, seed=3)[0]
    print(f"Alimentation : {feed.solids_tph} t/h | Cu = {feed.assays.get('Cu', 0):.2f} %\n")

    # Trois cellules successives, car en pratique on flotte en plusieurs cellules : ainsi
    # chaque cellule récupère une part du Cu restant dans le rejet de la précédente.
    cell = lambda: SeparationUnit("flotation", {"collector_gpt": 100, "pulp_ph": 9.0,
                                                "residence_min": 5, "rotor_speed_rpm": 1200})
    stages = [("cell1", cell()), ("cell2", cell()), ("cell3", cell())]

    result = run_series(feed, stages)

    cu_cumule = 0.0
    for name, conc in result["concentrates"].items():
        cu_g = conc.assays.get("Cu", 0) * conc.solids_tph
        cu_cumule += cu_g
        print(f"  {name}: {conc.solids_tph:5.1f} t/h | Cu={conc.assays.get('Cu', 0):.2f}% "
              f"| Cu cumulé récupéré = {cu_cumule:.2f} g·%")

    conc_total, tail, feed_m, somme = mass_check(result)
    print(f"\nRejet final : {tail:.1f} t/h | Cu={result['final_tail'].assays.get('Cu', 0):.2f}%")
    print(f"Conservation masse : concentrés {conc_total:.1f} + rejet {tail:.1f} "
          f"= {somme:.1f} t/h (alim. {feed_m})")