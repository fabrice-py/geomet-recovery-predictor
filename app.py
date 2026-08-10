"""
app.py
Interface web du simulateur geometallurgique (Streamlit).

Minerai : trois modes (profil predefini, mineralogie composee depuis la base, mineraux
personnalises hors base). Traitement : separation SIMPLE (une unite) ou CIRCUIT multi-etages
(flottation differentielle predefinie). Les circuits fonctionnent sur profils/base, car la
propagation des proprietes custom a travers un circuit reste a faire (V3.5).

L'interface ne fait qu'habiller la logique de src/ (principe logique/presentation separe).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pandas as pd
import streamlit as st

from feed_generator import generate_feed
from mineralogy import ORE_PROFILES, MINERALS, assays_from_modal
from data_models import Stream, LiberationState
from separation import SeparationUnit, SEPARATION_SPECS, separate
from laws_gravity import gravity_recovery, gravity_cutpoint
from laws_magnetic import magnetic_recovery, magnetic_cutpoint
from laws_flotation import flotation_recovery, gold_flotation_recovery
from circuit_cu_zn import run_differential_circuit, build_stages


XRF_ELEMENTS = [
    "Fe", "Cu", "Zn", "Pb", "Au", "Ag", "Ni", "Co", "Sn", "W", "Mn", "Ti", "Cr", "V",
    "U", "Mo", "SiO2", "Al2O3", "CaO", "MgO", "K", "Na", "P", "S", "As", "Sb", "Bi", "F",
]
MAGNETIC_CATEGORIES = ["ferromagnetique", "paramagnetique",
                       "paramagnetique_faible", "diamagnetique"]

# Circuits predefinis, decrits comme DONNEE (liste d'etages), car un circuit differentiel
# n'est qu'une sequence d'etages avec leur chimie : ainsi on reutilise run_differential_circuit.
CIRCUITS_PREDEFINIS = {
    "Differentiel Cu -> Zn": [
        {"name": "Cu", "pulp_ph": 9.0,  "collector_gpt": 100,
         "depressed_minerals": ["sphalerite"]},
        {"name": "Zn", "pulp_ph": 10.5, "collector_gpt": 120,
         "activated_minerals": ["sphalerite"]},
    ],
    "Differentiel Pb -> Cu -> Zn": [
        {"name": "Pb", "pulp_ph": 8.5,  "collector_gpt": 80,
         "depressed_minerals": ["sphalerite", "chalcopyrite", "pyrite_co"]},
        {"name": "Cu", "pulp_ph": 9.5,  "collector_gpt": 100,
         "depressed_minerals": ["sphalerite", "pyrite_co"]},
        {"name": "Zn", "pulp_ph": 10.5, "collector_gpt": 120,
         "activated_minerals": ["sphalerite"]},
    ],
}


st.set_page_config(page_title="Simulateur geometallurgique", layout="wide")
st.title("Simulateur geometallurgique de separation")
st.caption("Choisissez un minerai, un traitement (separation simple ou circuit) et ses "
           "reglages : l'outil predit les concentres, le rejet et les teneurs.")


# ============================ BARRE LATERALE : MINERAI ============================
st.sidebar.header("1. Minerai")

feed_tph = st.sidebar.number_input("Debit d'alimentation (t/h)",
                                   min_value=1.0, max_value=10000.0, value=100.0, step=10.0)

mode_minerai = st.sidebar.radio(
    "Mode", ["Profil predefini", "Mineralogie (base)", "Mineraux personnalises"])

profile_name = None
custom_modal = None
use_custom_minerals = False

if mode_minerai == "Profil predefini":
    profile_name = st.sidebar.selectbox("Profil", options=list(ORE_PROFILES.keys()))
elif mode_minerai == "Mineralogie (base)":
    st.sidebar.markdown("**Composez depuis la base** (% de chaque phase)")
    custom_modal = {}
    for mineral in MINERALS.keys():
        pct = st.sidebar.slider(mineral, 0.0, 100.0, 0.0, step=0.5)
        if pct > 0:
            custom_modal[mineral] = pct
    total_saisi = sum(custom_modal.values())
    if total_saisi == 0:
        st.sidebar.warning("Ajoutez au moins une phase (proportion > 0).")
    elif abs(total_saisi - 100.0) < 0.01:
        st.sidebar.success(f"Total : {total_saisi:.1f} %")
    else:
        st.sidebar.info(f"Total : {total_saisi:.1f} % -> renormalise a 100 %")
else:
    use_custom_minerals = True
    st.sidebar.markdown("**Mineraux personnalises**")
    st.sidebar.caption("Definissez vos phases dans la zone principale, puis reglez le "
                       "traitement ici. (Non disponible pour les circuits en V3-A.)")

p80 = st.sidebar.slider("P80 (um) - finesse de broyage", 45.0, 300.0, 150.0, step=5.0)
liberation_deg = st.sidebar.slider("Degre de liberation moyen", 0.0, 1.0, 0.85, step=0.05)


# ============================ BARRE LATERALE : TRAITEMENT ============================
st.sidebar.header("2. Traitement")
traitement = st.sidebar.radio("Type", ["Separation simple", "Circuit"])

unit_type = None
settings = {}
circuit_name = None

if traitement == "Separation simple":
    st.sidebar.subheader("Voie de separation")
    voies = ["shaking_table", "spiral", "falcon", "magnetic", "flotation"]
    unit_type = st.sidebar.selectbox("Type d'unite", options=voies)

    st.sidebar.subheader("Reglages machine")
    for param, rule in SEPARATION_SPECS[unit_type].items():
        if param.startswith("_"):
            continue
        if "choices" in rule:
            settings[param] = st.sidebar.selectbox(
                param, options=rule["choices"], index=rule["choices"].index(rule["default"]))
        elif "min" in rule:
            settings[param] = st.sidebar.slider(
                param, float(rule["min"]), float(rule["max"]), float(rule["default"]))
else:
    st.sidebar.subheader("Circuit predefini")
    circuit_name = st.sidebar.selectbox("Circuit", options=list(CIRCUITS_PREDEFINIS.keys()))
    if use_custom_minerals:
        st.sidebar.error("Les circuits ne sont pas disponibles pour les mineraux "
                         "personnalises en V3-A. Choisissez un profil ou la mineralogie de base.")

lancer = st.sidebar.button("Lancer", type="primary")


# ============================ ZONE PRINCIPALE : SAISIE CUSTOM ============================
custom_props = None
custom_chem = None
if use_custom_minerals:
    st.header("Definition des mineraux personnalises")
    st.markdown("**Tableau 1 - Proprietes physiques.** Une ligne par mineral.")
    default_props = pd.DataFrame([
        {"mineral": "mon_mineral_1", "proportion_%": 5.0, "densite_g_cm3": 4.2,
         "magnetique": "paramagnetique_faible", "flottabilite_0_1": 0.9},
        {"mineral": "gangue", "proportion_%": 95.0, "densite_g_cm3": 2.65,
         "magnetique": "diamagnetique", "flottabilite_0_1": 0.1},
    ])
    custom_props = st.data_editor(
        default_props, num_rows="dynamic", use_container_width=True,
        column_config={
            "magnetique": st.column_config.SelectboxColumn(options=MAGNETIC_CATEGORIES),
            "flottabilite_0_1": st.column_config.NumberColumn(min_value=0.0, max_value=1.0),
        }, key="props_editor")

    st.markdown("**Tableau 2 - Composition chimique (% massique, type XRF).**")
    minerals_list = [m for m in custom_props["mineral"].tolist() if str(m).strip()]
    chem_init = pd.DataFrame({"mineral": minerals_list})
    for el in XRF_ELEMENTS:
        chem_init[el] = 0.0
    custom_chem = st.data_editor(chem_init, use_container_width=True, key="chem_editor")

    for _, row in custom_chem.iterrows():
        total_el = sum(row[el] for el in XRF_ELEMENTS)
        if row["mineral"] and abs(total_el - 100.0) > 5.0:
            st.warning(f"Le mineral '{row['mineral']}' totalise {total_el:.1f} % "
                       f"(attendu ~100 %). Verifiez la composition.")


# ============================ AIGUILLAGE (separation simple) ============================
def apply_unit_ui(stream, unit, prop_lookup=None, assay_func=None):
    """Aiguillage vers la bonne loi selon la voie, avec proprietes et chimie custom."""
    if unit.unit_type in ("shaking_table", "spiral", "falcon"):
        d50, ep = gravity_cutpoint(unit)
        reco = gravity_recovery(stream, d50, ep, densities=prop_lookup)
        return separate(stream, reco, assay_func=assay_func)
    elif unit.unit_type == "magnetic":
        thr, sharp = magnetic_cutpoint(unit)
        reco = magnetic_recovery(stream, thr, sharp, mineral_props=prop_lookup)
        return separate(stream, reco, assay_func=assay_func)
    else:
        reco = flotation_recovery(stream, unit, mineral_props=prop_lookup)
        au = gold_flotation_recovery(stream, reco, unit)
        return separate(stream, reco, gold_recovery=au, assay_func=assay_func)


def build_feed():
    """Construit le flux d'alimentation selon le mode de minerai choisi."""
    prop_lookup = None
    assay_func = None

    if profile_name is not None:
        feed = generate_feed(profile_name, n_samples=1, seed=42, feed_tph=feed_tph)[0]
        feed.p80_um = p80
        feed.liberation = LiberationState(degree={m: liberation_deg for m in feed.modal})
        return feed, prop_lookup, assay_func

    if custom_modal is not None:
        total = sum(custom_modal.values())
        if total == 0:
            st.error("Ajoutez au moins une phase minerale (proportion > 0).")
            st.stop()
        modal = {m: round(v / total * 100, 3) for m, v in custom_modal.items()}
        assays = assays_from_modal(modal)
        lib = LiberationState(degree={m: liberation_deg for m in modal})
        feed = Stream(name="minerai_base", solids_tph=feed_tph, modal=modal,
                      liberation=lib, p80_um=p80, assays=assays)
        return feed, prop_lookup, assay_func

    # mineraux personnalises
    props = custom_props.copy()
    props = props[props["mineral"].astype(str).str.strip() != ""]
    props["proportion_%"] = pd.to_numeric(props["proportion_%"], errors="coerce").fillna(0.0)
    props["densite_g_cm3"] = pd.to_numeric(props["densite_g_cm3"], errors="coerce").fillna(2.65)
    props["flottabilite_0_1"] = pd.to_numeric(props["flottabilite_0_1"], errors="coerce").fillna(0.1)
    props = props[props["proportion_%"] > 0]
    if len(props) == 0:
        st.error("Definissez au moins un mineral avec une proportion > 0.")
        st.stop()
    total = props["proportion_%"].sum()
    modal = {r["mineral"]: round(r["proportion_%"] / total * 100, 3) for _, r in props.iterrows()}
    prop_lookup = {}
    for _, r in props.iterrows():
        prop_lookup[r["mineral"]] = {
            "density": float(r["densite_g_cm3"]),
            "magnetic": r["magnetique"],
            "floatability": float(r["flottabilite_0_1"]),
        }
    chem_indexed = custom_chem.set_index("mineral")

    def custom_assay_func(modal_dict):
        out = {}
        for mineral, pct in modal_dict.items():
            if mineral in chem_indexed.index:
                for el in XRF_ELEMENTS:
                    val = chem_indexed.loc[mineral, el]
                    frac = (float(val) if pd.notna(val) else 0.0) / 100.0
                    if frac > 0:
                        out[el] = out.get(el, 0.0) + pct * frac
        return {el: round(v, 3) for el, v in out.items()}

    assays = custom_assay_func(modal)
    assay_func = custom_assay_func
    lib = LiberationState(degree={m: liberation_deg for m in modal})
    feed = Stream(name="minerai_custom", solids_tph=feed_tph, modal=modal,
                  liberation=lib, p80_um=p80, assays=assays)
    return feed, prop_lookup, assay_func


def show_teneurs(streams_named, feed):
    """Affiche un tableau de teneurs avec une colonne par flux (alimentation + produits)."""
    all_elements = set(feed.assays)
    for _, s in streams_named:
        all_elements |= set(s.assays)
    elements = sorted(all_elements)
    rows = []
    for el in elements:
        row = {"Element": el, "Alimentation": round(feed.assays.get(el, 0), 3)}
        for name, s in streams_named:
            row[name] = round(s.assays.get(el, 0), 3)
        rows.append(row)
    st.dataframe(rows, use_container_width=True)


# ============================ LANCEMENT ============================
if lancer:
    feed, prop_lookup, assay_func = build_feed()

    st.header("Resultats")
    st.subheader("Mineralogie de l'alimentation (%)")
    st.dataframe([{"Mineral": m, "%": round(v, 2)} for m, v in feed.modal.items()],
                 use_container_width=True)

    if traitement == "Separation simple":
        unit = SeparationUnit(unit_type, settings)
        conc, rejet = apply_unit_ui(feed, unit, prop_lookup=prop_lookup, assay_func=assay_func)

        c1, c2, c3 = st.columns(3)
        c1.metric("Alimentation", f"{feed.solids_tph:.0f} t/h")
        c2.metric("Concentre", f"{conc.solids_tph:.1f} t/h")
        c3.metric("Rejet", f"{rejet.solids_tph:.1f} t/h")

        st.subheader("Teneurs (%)")
        show_teneurs([("Concentre", conc), ("Rejet", rejet)], feed)
        st.caption(f"Voie : {unit_type} | P80 : {feed.p80_um:.0f} um | "
                   f"Liberation : {liberation_deg:.2f}")

    else:  # Circuit
        if use_custom_minerals:
            st.error("Les circuits ne sont pas disponibles pour les mineraux personnalises "
                     "en V3-A. Choisissez un profil ou la mineralogie de base.")
            st.stop()

        stage_configs = CIRCUITS_PREDEFINIS[circuit_name]
        result = run_differential_circuit(feed, stage_configs)

        # Affichage des concentres successifs + rejet final.
        concentrates = result["concentrates"]
        tail = result["final_tail"]

        cols = st.columns(len(concentrates) + 2)
        cols[0].metric("Alimentation", f"{feed.solids_tph:.0f} t/h")
        for i, (name, conc) in enumerate(concentrates.items(), start=1):
            cols[i].metric(f"Conc. {name}", f"{conc.solids_tph:.1f} t/h")
        cols[-1].metric("Rejet final", f"{tail.solids_tph:.1f} t/h")

        st.subheader("Teneurs (%) par produit")
        streams_named = [(f"Conc. {name}", conc) for name, conc in concentrates.items()]
        streams_named.append(("Rejet final", tail))
        show_teneurs(streams_named, feed)

        # Controle de conservation de la masse.
        total_out = sum(c.solids_tph for c in concentrates.values()) + tail.solids_tph
        st.caption(f"Circuit : {circuit_name} | Conservation masse : {total_out:.1f} t/h "
                   f"(alimentation {feed.solids_tph:.0f} t/h)")
else:
    if not use_custom_minerals:
        st.info("Configurez le minerai et le traitement dans la barre laterale, "
                "puis cliquez sur **Lancer**.")