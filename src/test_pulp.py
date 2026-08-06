"""
test_pulp.py
Vérification manuelle de close_pulp sur des flux générés, car un calcul physique doit
toujours être confronté à un contrôle de bon sens : ainsi on compare la densité de
pulpe d'un minerai de fer (dense) à celle d'un polymétallique, à % solides égal.
"""

from feed_generator import generate_feed
from mineral_properties import get_densities

densites = get_densities()

for profil in ["iron_flotation", "polymetallic_refractory_au"]:
    # Génération d'un seul flux à % solides fixé, car on veut comparer à conditions
    # égales : ainsi seule la minéralogie (donc la densité) diffère.
    flux = generate_feed(profil, n_samples=1, seed=7)[0]
    flux.pct_solids_mass = 35.0          # on impose le meme % solides aux deux
    flux.close_pulp(densites)

    print(f"\n=== {profil} ===")
    print(flux.summary())
    print(f"  Densite du solide : {flux.solid_sg} g/cm3")
    print(f"  Debit d'eau       : {flux.water_tph} t/h (pour {flux.solids_tph} t/h solides)")
    print(f"  Densite de pulpe  : {flux.pulp_sg} g/cm3")