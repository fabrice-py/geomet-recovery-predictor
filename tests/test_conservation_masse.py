"""Tests de conservation de masse : l'invariant physique le plus important. Une separation,
un circuit, ou une charge circulante ne doit jamais faire apparaitre ni disparaitre de la
masse. Si un de ces tests casse un jour, c'est qu'une modification a rompu la physique."""
import pytest
from feed_generator import generate_feed, apply_p80
from separation import SeparationUnit
from circuit import run_series
from classification import classify_stream
from flowsheet import make_flowsheet, solve_iterative
from size_classes import DEFAULT_GRID_UM


def make_test_feed(p80=150):
    """Un minerai de test reproductible."""
    f = generate_feed("polymetallic_au_cu_zn_pb", 1, seed=42)[0]
    apply_p80(f, p80)
    return f


def test_separation_conserve_masse():
    """Concentre + rejet = alimentation, car separer ne fait que repartir la masse."""
    from laws_flotation import flotation_recovery, gold_flotation_recovery
    from separation import separate
    f = make_test_feed()
    unit = SeparationUnit("flotation", {"collector_type": "xanthate_SIBX",
        "collector_gpt": 150, "frother_gpt": 25, "pulp_ph": 7.0,
        "residence_min": 8, "rotor_speed_rpm": 1200,
        "activated_minerals": ["pyrite_co", "arsenopyrite"]})
    reco = flotation_recovery(f, unit)
    conc, rejet = separate(f, reco)
    assert abs((conc.solids_tph + rejet.solids_tph) - f.solids_tph) < 1e-6


def test_run_series_conserve_masse():
    """Somme des concentres + rejet final = alimentation (circuit serie)."""
    f = make_test_feed()
    stages = [
        ("table", SeparationUnit("shaking_table", {"deck_slope_deg": 4.0,
            "stroke_freq_hz": 5.5, "wash_water_lpm": 20})),
        ("flot", SeparationUnit("flotation", {"collector_type": "xanthate_SIBX",
            "collector_gpt": 150, "frother_gpt": 25, "pulp_ph": 7.0,
            "residence_min": 8, "rotor_speed_rpm": 1200,
            "activated_minerals": ["pyrite_co"]})),
    ]
    result = run_series(f, stages, grid=DEFAULT_GRID_UM, apply_p80_func=apply_p80)
    total = sum(c.solids_tph for c in result["concentrates"].values())
    total += result["final_tail"].solids_tph
    assert abs(total - f.solids_tph) < 1e-4


def test_cyclone_conserve_masse():
    """Overflow + underflow = alimentation, car le cyclone ne fait que classer par taille."""
    f = make_test_feed()
    over, under = classify_stream(f, diameter_cm=15, pressure_kpa=100,
                                  grid=DEFAULT_GRID_UM, apply_p80_func=apply_p80)
    assert abs((over.solids_tph + under.solids_tph) - f.solids_tph) < 1e-3


def test_charge_circulante_conserve_masse():
    """Au regime permanent, somme des produits FINAL = alimentation fraiche. C'est LE test
    crucial : la charge circulante tourne en boucle mais ne cree ni ne detruit de masse."""
    f = make_test_feed(p80=200)
    fs = make_flowsheet(
        nodes={
            "cyclone": {"unit_type": "hydrocyclone", "settings": {"diameter_cm": 15.0, "pressure_kpa": 100.0}},
            "broyeur": {"unit_type": "ball_mill", "settings": {"work_index": 15.0, "energy_kwht": 12.0}},
            "flot": {"unit_type": "flotation", "settings": {"collector_type": "xanthate_SIBX",
                "collector_gpt": 150, "frother_gpt": 25, "pulp_ph": 7.0, "residence_min": 8,
                "rotor_speed_rpm": 1200, "activated_minerals": ["pyrite_co"]}},
        },
        connections=[
            {"from": ("FEED", "out"), "to": "cyclone"},
            {"from": ("cyclone", "overflow"), "to": "flot"},
            {"from": ("cyclone", "underflow"), "to": "broyeur"},
            {"from": ("broyeur", "out"), "to": "cyclone"},
            {"from": ("flot", "concentre"), "to": "FINAL"},
            {"from": ("flot", "rejet"), "to": "FINAL"},
        ],
    )
    res = solve_iterative(fs, f, grid=DEFAULT_GRID_UM, apply_p80_func=apply_p80)
    assert res["status"] == "converged"
    total_final = sum(s.solids_tph for _, s in res["finals"])
    # Tolerance un peu plus large car la convergence s'arrete au seuil (0.1%).
    assert abs(total_final - f.solids_tph) < 0.5