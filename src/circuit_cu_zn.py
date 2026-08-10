"""
circuit_cu_zn.py
Circuits de flottation différentielle configurables, car un circuit ne doit pas être
codé en dur pour un couple de métaux précis : ainsi un circuit se décrit comme une
LISTE D'ÉTAGES (donnée), chaque étage nommant le collecteur, le pH et les minéraux à
déprimer ou activer, et la même mécanique de chaînage traite n'importe quelle séquence.
"""

from feed_generator import generate_feed
from separation import SeparationUnit
from circuit import run_series


def build_stages(stage_configs):
    """
    Construction de la liste d'unités à partir de descriptions d'étages, car on veut
    décrire un circuit sans écrire de logique : ainsi chaque config (un dict) devient une
    SeparationUnit prête pour run_series, les réglages absents prenant leurs défauts.
    """
    stages = []
    for cfg in stage_configs:
        name = cfg["name"]
        settings = {k: v for k, v in cfg.items() if k != "name"}
        settings.setdefault("collector_type", "xanthate_SIBX")
        stages.append((name, SeparationUnit("flotation", settings)))
    return stages


def run_differential_circuit(feed, stage_configs, prop_lookup=None, assay_func=None):
    """
    Application d'un circuit différentiel décrit par ses étages, car la séquence et la
    chimie de chaque étage définissent entièrement la séparation : ainsi on construit les
    unités puis on délègue le chaînage à run_series, déjà générique.
    """
    stages = build_stages(stage_configs)
    return run_series(feed, stages, prop_lookup=prop_lookup, assay_func=assay_func)


def print_circuit_result(feed, result, metals=("Cu", "Zn")):
    """
    Affichage synthétique d'un circuit, car on veut lire les concentrés et le rejet d'un
    coup : ainsi on montre la masse et les teneurs des métaux suivis pour chaque produit.
    """
    header = "  ".join(f"{m}=%" for m in metals)
    print(f"ALIMENTATION : {feed.solids_tph} t/h | " +
          " ".join(f"{m}={feed.assays.get(m, 0):.2f}%" for m in metals) + "\n")

    for name, conc in result["concentrates"].items():
        line = " ".join(f"{m}={conc.assays.get(m, 0):5.2f}%" for m in metals)
        print(f"  {name:14s} {conc.solids_tph:5.1f} t/h | {line}")

    tail = result["final_tail"]
    line = " ".join(f"{m}={tail.assays.get(m, 0):5.2f}%" for m in metals)
    print(f"  {'rejet_final':14s} {tail.solids_tph:5.1f} t/h | {line}")

    total = sum(c.solids_tph for c in result["concentrates"].values()) + tail.solids_tph
    print(f"\nConservation masse : {total:.1f} t/h (alim. {feed.solids_tph})")


if __name__ == "__main__":
    feed = generate_feed("polymetallic_refractory_au", n_samples=1, seed=3)[0]

    # Le circuit Cu -> Zn décrit comme de la DONNEE, car on veut le reconfigurer sans
    # toucher au code : ainsi l'etage cuivre deprime la sphalerite et l'etage zinc l'active.
    circuit_cu_zn = [
        {"name": "Cu", "pulp_ph": 9.0,  "collector_gpt": 100,
         "depressed_minerals": ["sphalerite"]},
        {"name": "Zn", "pulp_ph": 10.5, "collector_gpt": 120,
         "activated_minerals": ["sphalerite"]},
    ]

    print("=== Circuit differentiel Cu -> Zn ===\n")
    result = run_differential_circuit(feed, circuit_cu_zn)
    print_circuit_result(feed, result, metals=("Cu", "Zn"))
    # Circuit Pb -> Cu -> Zn a trois etages, car un minerai a galene se traite en
    # sequence : ainsi on flotte d'abord le plomb (en deprimant Cu et Zn), puis le
    # cuivre (en deprimant Zn), puis le zinc active - sans aucune logique nouvelle.
    feed3 = generate_feed("polymetallic_pb_cu_zn", n_samples=1, seed=5)[0]
    circuit_pb_cu_zn = [
        {"name": "Pb", "pulp_ph": 8.5,  "collector_gpt": 80,
         "depressed_minerals": ["sphalerite", "chalcopyrite", "pyrite_co"]},
        {"name": "Cu", "pulp_ph": 9.5,  "collector_gpt": 100,
         "depressed_minerals": ["sphalerite", "pyrite_co"]},
        {"name": "Zn", "pulp_ph": 10.5, "collector_gpt": 120,
         "activated_minerals": ["sphalerite"]},
    ]

    print("\n=== Circuit differentiel Pb -> Cu -> Zn (3 etages) ===\n")
    result3 = run_differential_circuit(feed3, circuit_pb_cu_zn)
    print_circuit_result(feed3, result3, metals=("Pb", "Cu", "Zn"))