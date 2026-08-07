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

def effective_floatability(mineral, unit_settings):
    """
    Flottabilité effective d'un minéral selon le collecteur et les modificateurs, car la
    sélectivité d'un circuit différentiel se pilote minéral par minéral : ainsi tout
    minéral listé comme déprimé est écrasé et tout minéral listé comme activé est rendu
    fortement flottable, quel qu'il soit (sphalérite, galène, pyrite...).
    """
    collector = unit_settings["collector_type"]

    # Flottation inverse : seule la gangue silicatée flotte.
    if collector == "amine_inverse":
        return 0.85 if mineral in ("quartz", "gangue_silicate") else 0.05

    # Dépression / activation génériques, car elles priment sur la flottabilité native :
    # ainsi on interroge les listes fournies par l'étage plutôt qu'un minéral en dur.
    if mineral in unit_settings.get("depressed_minerals", []):
        return 0.05                          # déprimé : reste au fond
    if mineral in unit_settings.get("activated_minerals", []):
        return 0.90                          # activé : flotte comme un bon sulfure

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
        floatab = effective_floatability(m, s)
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
    # Test : flottation directe d'un minerai polymétallique, car on veut voir les
    # sulfures (chalcopyrite en tête) monter dans la mousse et la gangue rester au rejet.
    from feed_generator import generate_feed
    from separation import separate, SeparationUnit

    flux = generate_feed("polymetallic_refractory_au", n_samples=1, seed=3)[0]
    print("Alimentation (minéralogie) :")
    for m, p in sorted(flux.modal.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {m:16s} {p:5.1f} %   (flottabilité {MINERAL_PROPERTIES[m]['floatability']})")

    unit = SeparationUnit("flotation", {"collector_gpt": 100, "residence_min": 8,
                                        "rotor_speed_rpm": 1200})
    reco = flotation_recovery(flux, unit)
    print("\nRécupération par minéral (flottation directe) :")
    for m, r in sorted(reco.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {m:16s} {r*100:5.1f} %")

    conc, rejet = separate(flux, reco)
    print(f"\nCu alimentation : {flux.assays.get('Cu', 0):.2f} %")
    print(f"Cu concentré    : {conc.assays.get('Cu', 0):.2f} %   (masse {conc.solids_tph:.1f} t/h)")
    print(f"Cu rejet        : {rejet.assays.get('Cu', 0):.2f} %")