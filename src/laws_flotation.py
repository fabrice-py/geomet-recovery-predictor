"""
laws_flotation.py
Loi de flottation par cinétique de premier ordre, car la flottation dépend du temps
contrairement aux autres voies : ainsi chaque minéral récupère selon
R = Rmax * (1 - exp(-k * t)), où sa flottabilité native fixe Rmax et k de référence,
que les réglages (collecteur, moussant, rotor) viennent ensuite moduler.

Modèle cinétique (macroscopique), car il accueille tous les réglages de conduite sans
exiger les données microscopiques de collision bulle-particule (extension Option B).
Ce fichier traite la flottation DIRECTE au xanthate (5a) ; pH et flottation inverse
viendront au 5b.
"""

import math

from mineral_properties import MINERAL_PROPERTIES


def kinetic_recovery(rmax, k, t):
    """
    Récupération cinétique de premier ordre, car la flottation progresse dans le temps
    vers un plateau : ainsi la récupération croît puis sature à Rmax.
    """
    return rmax * (1.0 - math.exp(-k * t))


def rotor_bell_factor(rpm, rpm_opt=1200.0, width=350.0):
    """
    Facteur cloche de l'agitation du rotor sur k, car il existe un optimum d'agitation :
    ainsi trop peu de rotation limite les collisions bulle-particule et trop de rotation
    détache les particules et fait coalescer les bulles, k chutant des deux côtés.
    """
    return math.exp(-((rpm - rpm_opt) ** 2) / (2 * width ** 2))

def effective_floatability(mineral, collector_type):
    """
    Flottabilité effective selon le collecteur, car un collecteur cible des minéraux
    précis : ainsi un xanthate rend flottables les sulfures (flottabilité native de la
    base), tandis qu'une amine rend flottable la gangue silicatée et rien d'autre.
    """
    if collector_type == "amine_inverse":
        if mineral in ("quartz", "gangue_silicate"):
            return 0.85
        return 0.05
    return MINERAL_PROPERTIES[mineral]["floatability"]


def ph_pyrite_factor(ph):
    """
    Facteur de dépression de la pyrite selon le pH, car la pyrite est déprimée en milieu
    alcalin : ainsi son Rmax reste plein à pH neutre et chute fortement vers pH 12.
    """
    return max(0.1, min(1.0, 1.0 - (ph - 8.0) / 4.0))


def flotation_recovery(stream, unit):
    """
    Récupération par minéral en flottation, car c'est le produit qu'attend separate() :
    ainsi on part de la flottabilité effective (selon le collecteur), on module k par la
    dose et l'agitation, Rmax par le moussant, on déprime la pyrite selon le pH, puis on
    convertit la fraction montée dans la mousse en récupération au concentré selon le
    sens (directe : mousse = concentré ; inverse : mousse = rejet).
    """
    s = unit.settings
    t = s["residence_min"]
    collector = s["collector_type"]
    reverse = (collector == "amine_inverse")

    dose_factor = 1.0 - math.exp(-s["collector_gpt"] / 80.0)
    bell = rotor_bell_factor(s["rotor_speed_rpm"])
    rmax_bonus = 0.10 * (1.0 - math.exp(-s["frother_gpt"] / 25.0))
    ph = s["pulp_ph"]

    recovery = {}
    for m in stream.modal:
        floatab = effective_floatability(m, collector)
        rmax = min(0.98, 0.02 + 0.95 * (floatab ** 2) + rmax_bonus)
        k = (0.15 + 1.60 * floatab) * dose_factor * bell

        # Dépression de la pyrite en milieu alcalin (uniquement flottation directe).
        if m == "pyrite_co" and not reverse:
            rmax *= ph_pyrite_factor(ph)

        float_frac = kinetic_recovery(rmax, k, t)   # fraction montant dans la mousse

        # Conversion mousse -> concentré, car en flottation inverse la mousse est le
        # rejet : ainsi le concentré récupère ce qui NE monte PAS.
        recovery[m] = round(1.0 - float_frac if reverse else float_frac, 4)
    return recovery


def gold_flotation_recovery(stream, mineral_recovery, unit):
    """
    Récupération de l'or au concentré, car l'or réfractaire n'a pas de flottabilité
    propre : ainsi il suit ses sulfures hôtes (moyenne pondérée par leur masse) tandis
    que l'or libre flotte mal. En flottation inverse (minerai de fer), pas d'or à traiter.
    """
    if unit.settings["collector_type"] == "amine_inverse":
        return 0.0
    refr = stream.assays.get("Au_refractory_frac", None)
    if refr is None:
        return 0.0                                  # profil sans or

    hosts = ["arsenopyrite", "pyrite_co"]
    host_mass = {h: stream.modal.get(h, 0.0) for h in hosts}
    total_host = sum(host_mass.values())
    host_recovery = (sum(mineral_recovery.get(h, 0.0) * host_mass[h] for h in hosts)
                     / total_host) if total_host > 1e-9 else 0.0

    free_gold_recovery = 0.20                       # l'or libre flotte mal en directe
    return round(refr * host_recovery + (1 - refr) * free_gold_recovery, 4)

if __name__ == "__main__":
    from feed_generator import generate_feed
    from separation import separate, SeparationUnit

    # 1. Flottation directe du polymétallique à deux pH, car on veut voir la pyrite
    #    se faire déprimer quand le pH monte (sélectivité chalcopyrite / pyrite).
    flux = generate_feed("polymetallic_refractory_au", n_samples=1, seed=3)[0]
    print(f"Or à l'alimentation : {flux.assays['Au_gt']} g/t "
          f"(réfractaire {flux.assays['Au_refractory_frac']*100:.0f} %)\n")

    for ph in [9.0, 11.5]:
        unit = SeparationUnit("flotation", {"collector_type": "xanthate_SIBX",
                                            "collector_gpt": 100, "pulp_ph": ph,
                                            "residence_min": 8, "rotor_speed_rpm": 1200})
        reco = flotation_recovery(flux, unit)
        au_reco = gold_flotation_recovery(flux, reco, unit)
        conc, rejet = separate(flux, reco, gold_recovery=au_reco)
        print(f"pH {ph:>4} | pyrite={reco['pyrite_co']*100:4.0f}% "
              f"chalco={reco['chalcopyrite']*100:4.0f}% | Au récup={au_reco*100:4.0f}% | "
              f"conc {conc.solids_tph:4.1f} t/h à Au={conc.assays.get('Au_gt', 0):.1f} g/t")

    # 2. Flottation inverse d'un minerai de fer, car on veut voir la silice partir dans
    #    la mousse (rejet) et l'hématite rester au concentré.
    print()
    flux_fe = generate_feed("iron_flotation", n_samples=1, seed=1)[0]
    unit_inv = SeparationUnit("flotation", {"collector_type": "amine_inverse"})
    reco_inv = flotation_recovery(flux_fe, unit_inv)
    conc_fe, rejet_fe = separate(flux_fe, reco_inv)
    print(f"Inverse (amine) | Fe alim={flux_fe.assays['Fe']:.1f}% -> "
          f"conc {conc_fe.solids_tph:.1f} t/h à Fe={conc_fe.assays['Fe']:.1f}% "
          f"(quartz récup conc={reco_inv['quartz']*100:.0f}%)")