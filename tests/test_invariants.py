"""Tests d'invariants physiques : proprietes que le modele doit TOUJOURS respecter, quels
que soient les reglages. Ils protegent la coherence physique (une PSD somme a 1, un broyeur
ne grossit pas, les bornes de parametres sont gardees)."""
import pytest
from size_classes import make_psd_rosin_rammler, p80_from_psd, DEFAULT_GRID_UM
from comminution import bond_product_p80
from separation import SeparationUnit


def test_psd_somme_un():
    """Une PSD Rosin-Rammler somme a 1, car c'est une distribution de fractions massiques."""
    for p80 in [50, 100, 150, 250]:
        psd = make_psd_rosin_rammler(DEFAULT_GRID_UM, p80, m=1.0)
        assert abs(sum(psd) - 1.0) < 1e-6


def test_psd_p80_coherent():
    """Le P80 derive d'une PSD generee pour un P80 vise doit coller au vise (a la resolution
    de la grille pres), car PSD et P80 doivent rester coherents."""
    for p80_vise in [60, 120, 200]:
        psd = make_psd_rosin_rammler(DEFAULT_GRID_UM, p80_vise, m=1.0)
        p80_derive = p80_from_psd(DEFAULT_GRID_UM, psd)
        # Tolerance large en zone grossiere (grille peu resolue au-dela de 150 um).
        assert abs(p80_derive - p80_vise) / p80_vise < 0.15


def test_bond_plus_energie_plus_fin():
    """Plus d'energie -> P80 de sortie plus fin, car la loi de Bond lie energie et reduction."""
    p80_5 = bond_product_p80(f80=150, work_index=15, energy_kwht=5)
    p80_10 = bond_product_p80(f80=150, work_index=15, energy_kwht=10)
    p80_20 = bond_product_p80(f80=150, work_index=15, energy_kwht=20)
    assert p80_5 > p80_10 > p80_20


def test_bond_durete_reduit_moins():
    """Un minerai plus dur (Wi eleve) est moins reduit a energie egale."""
    p80_tendre = bond_product_p80(f80=150, work_index=10, energy_kwht=10)
    p80_dur = bond_product_p80(f80=150, work_index=20, energy_kwht=10)
    assert p80_dur > p80_tendre   # plus dur -> reste plus grossier


def test_bond_ne_grossit_jamais():
    """Un broyeur ne peut que reduire : le P80 de sortie <= F80, meme a energie nulle."""
    for f80 in [50, 100, 200]:
        p80_out = bond_product_p80(f80=f80, work_index=15, energy_kwht=0)
        assert p80_out <= f80 + 1e-9


def test_separation_unit_hors_bornes():
    """Un reglage hors bornes doit lever ValueError, car le registre valide les entrees."""
    with pytest.raises(ValueError):
        # deck_slope_deg va de 1.5 a 6.0 ; 50 est hors bornes.
        SeparationUnit("shaking_table", {"deck_slope_deg": 50.0,
            "stroke_freq_hz": 5.5, "wash_water_lpm": 20})


def test_separation_unit_valide_ok():
    """Un reglage dans les bornes ne leve pas d'erreur."""
    unit = SeparationUnit("shaking_table", {"deck_slope_deg": 3.0,
        "stroke_freq_hz": 5.5, "wash_water_lpm": 20})
    assert unit.unit_type == "shaking_table"