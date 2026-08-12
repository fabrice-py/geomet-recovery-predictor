"""
app.py
Interface web du simulateur geometallurgique (Streamlit).

Onglet Simulateur : minerai (profil / base / mineraux custom), separation simple ou circuit.
Chaque simulation affiche un tableau de PERFORMANCE (masse, recup massique, teneur, recup
metallurgique du metal d'interet) puis une section COURBE teneur-recuperation, coherente
avec le point simule (memes minerai et reglages, on balaye un parametre autour du point).

L'interface habille la logique de src/ (principe logique/presentation separe).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

from feed_generator import generate_feed
from mineralogy import ORE_PROFILES, MINERALS, assays_from_modal
from data_models import Stream, LiberationState
from separation import SeparationUnit, SEPARATION_SPECS, separate
from laws_gravity import gravity_recovery, gravity_cutpoint
from laws_magnetic import magnetic_recovery, magnetic_cutpoint
from laws_flotation import flotation_recovery, gold_flotation_recovery
from circuit_cu_zn import run_differential_circuit
from geomet_curves import (performance_row, grade_recovery_simple, grade_recovery_circuit, kinetics_curve)


XRF_ELEMENTS = [
    "Fe", "Cu", "Zn", "Pb", "Au", "Ag", "Ni", "Co", "Sn", "W", "Mn", "Ti", "Cr", "V",
    "U", "Mo", "SiO2", "Al2O3", "CaO", "MgO", "K", "Na", "P", "S", "As", "Sb", "Bi", "F",
]
MAGNETIC_CATEGORIES = ["ferromagnetique", "paramagnetique",
                       "paramagnetique_faible", "diamagnetique"]

CIRCUIT_TEMPLATES = {
    "Vierge (2 etages)": pd.DataFrame([
        {"name": "etage_1", "collector_gpt": 100.0, "pulp_ph": 9.0,
         "depressed_minerals": "", "activated_minerals": ""},
        {"name": "etage_2", "collector_gpt": 100.0, "pulp_ph": 10.0,
         "depressed_minerals": "", "activated_minerals": ""},
    ]),
    "Differentiel Cu -> Zn": pd.DataFrame([
        {"name": "Cu", "collector_gpt": 100.0, "pulp_ph": 9.0,
         "depressed_minerals": "sphalerite", "activated_minerals": ""},
        {"name": "Zn", "collector_gpt": 120.0, "pulp_ph": 10.5,
         "depressed_minerals": "", "activated_minerals": "sphalerite"},
    ]),
    "Differentiel Pb -> Cu -> Zn": pd.DataFrame([
        {"name": "Pb", "collector_gpt": 80.0, "pulp_ph": 8.5,
         "depressed_minerals": "sphalerite, chalcopyrite, pyrite_co", "activated_minerals": ""},
        {"name": "Cu", "collector_gpt": 100.0, "pulp_ph": 9.5,
         "depressed_minerals": "sphalerite, pyrite_co", "activated_minerals": ""},
        {"name": "Zn", "collector_gpt": 120.0, "pulp_ph": 10.5,
         "depressed_minerals": "", "activated_minerals": "sphalerite"},
    ]),
}

# Parametres balayables par voie (pour la courbe), car chaque voie a ses leviers numeriques :
# ainsi on ne propose au balayage que des reglages continus pertinents.
SWEEP_PARAMS = {
    "shaking_table": ["deck_slope_deg", "wash_water_lpm", "feed_rate_tph"],
    "spiral": ["wash_water_lpm", "feed_rate_tph"],
    "falcon": ["g_force", "fluidization_lpm"],
    "magnetic": ["field_tesla"],
    "flotation": ["collector_gpt", "pulp_ph", "residence_min"],
}


st.set_page_config(page_title="Simulateur geometallurgique", layout="wide")
st.title("Simulateur geometallurgique de separation")


# ============================ FONCTIONS PARTAGEES ============================
def apply_unit_ui(stream, unit, prop_lookup=None, assay_func=None):
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


def parse_minerals(cell):
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return []
    return [m.strip() for m in str(cell).split(",") if m.strip()]


def editor_to_stage_configs(df):
    configs = []
    for _, r in df.iterrows():
        name = str(r.get("name", "")).strip()
        if not name:
            continue
        configs.append({
            "name": name,
            "collector_gpt": float(pd.to_numeric(r.get("collector_gpt"), errors="coerce") or 100.0),
            "pulp_ph": float(pd.to_numeric(r.get("pulp_ph"), errors="coerce") or 9.0),
            "depressed_minerals": parse_minerals(r.get("depressed_minerals")),
            "activated_minerals": parse_minerals(r.get("activated_minerals")),
        })
    return configs


def perf_table(feed, streams_named, element):
    """Tableau de performance : une ligne par produit, avec masse, recup massique, teneur
    et recup metallurgique du metal d'interet."""
    rows = []
    for name, s in streams_named:
        r = performance_row(feed, s, element)
        rows.append({"Produit": name, **r})
    st.dataframe(rows, use_container_width=True)


def plot_grade_recovery(points, element, sweep_param, title):
    """Trace la courbe teneur-recuperation a partir des points calcules, avec detection
    des cas ou le metal suivi ne reagit quasiment pas au parametre (courbe non parlante)."""
    reco = [p["recup_metal_%"] for p in points]
    grade = [p["teneur_%"] for p in points]
    vals = [p["param"] for p in points]

   # Amplitudes RELATIVES, car juger "negligeable" en absolu depend de l'echelle : ainsi
    # on rapporte la variation a la valeur moyenne, et l'on n'avertit que si recuperation
    # ET teneur sont toutes deux quasi constantes (aucune courbe exploitable).
    amp_reco = max(reco) - min(reco) if reco else 0.0
    amp_grade = max(grade) - min(grade) if grade else 0.0
    mean_reco = (sum(reco) / len(reco)) if reco else 1.0
    mean_grade = (sum(grade) / len(grade)) if grade else 1.0
    rel_reco = amp_reco / mean_reco if mean_reco > 1e-9 else 0.0
    rel_grade = amp_grade / mean_grade if mean_grade > 1e-9 else 0.0
    # Seuil relatif a 0.5 % : en dessous, la variable est consideree plate.
    if rel_reco < 0.005 and rel_grade < 0.005:
        st.warning(
            f"Le metal suivi ({element}) ne reagit quasiment pas au parametre "
            f"'{sweep_param}' : recuperation varie de {amp_reco:.2f} pt, teneur de "
            f"{amp_grade:.2f} pt. Ce n'est probablement pas le bon levier pour ce metal. "
            f"Essayez un autre metal d'interet, ou un parametre qui mobilise ce metal "
            f"(ex. collecteur/temps pour un metal flotte directement). La courbe "
            f"ci-dessous reste affichee a titre indicatif.")

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(reco, grade, "o-", color="#C62828", lw=2, markersize=6)
    for r, g, v in zip(reco, grade, vals):
        ax.annotate(f"{v:.1f}", (r, g), fontsize=7, alpha=0.6,
                    textcoords="offset points", xytext=(4, 4))
    ax.set_xlabel(f"Recuperation metallurgique {element} (%)")
    ax.set_ylabel(f"Teneur {element} concentre (%)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig)

    st.subheader("Points de la courbe")
    st.dataframe([{sweep_param: p["param"], "Recup metal %": p["recup_metal_%"],
                   "Teneur %": p["teneur_%"], "Recup massique %": p["recup_massique_%"]}
                  for p in points], use_container_width=True)


# ============================ SIDEBAR : MINERAI ============================
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
    st.sidebar.caption("Definissez vos phases dans la zone principale.")

p80 = st.sidebar.slider("P80 (um)", 10.0, 300.0, 150.0, step=1.0)
liberation_deg = st.sidebar.slider("Degre de liberation moyen", 0.0, 1.0, 0.85, step=0.05)

# Metal d'interet, car les recuperations et la courbe se lisent pour un metal precis :
# ainsi l'utilisateur choisit lequel suivre (le simulateur reste agnostique au role).
st.sidebar.header("2. Metal d'interet")
element = st.sidebar.selectbox(
    "Metal suivi (recuperations et courbe)",
    options=["Fe", "Cu", "Zn", "Pb", "SiO2", "Au", "Ag", "Sn", "Ni", "Co", "As", "S"])

# ============================ SIDEBAR : TRAITEMENT ============================
st.sidebar.header("3. Traitement")
traitement = st.sidebar.radio("Type", ["Separation simple", "Circuit"])

unit_type = None
settings = {}
template_name = None

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
    st.sidebar.subheader("Circuit compose")
    template_name = st.sidebar.selectbox("Partir d'un modele",
                                         options=list(CIRCUIT_TEMPLATES.keys()))
    st.sidebar.caption("Le tableau des etages s'edite dans la zone principale.")

lancer = st.sidebar.button("Lancer", type="primary")


# ============================ ZONE PRINCIPALE : SAISIE ============================
custom_props = None
custom_chem = None
if use_custom_minerals:
    st.header("Definition des mineraux personnalises")
    st.markdown("**Tableau 1 - Proprietes physiques.**")
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

circuit_editor = None
if traitement == "Circuit":
    st.header("Composition du circuit")
    st.markdown("**Chaque ligne est un etage** applique en serie. Deprimer/activer : "
                "noms de mineraux separes par des virgules.")
    st.caption("Mineraux de la base : " + ", ".join(MINERALS.keys()))
    circuit_editor = st.data_editor(
        CIRCUIT_TEMPLATES[template_name], num_rows="dynamic",
        use_container_width=True, key="circuit_editor")


def build_feed():
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

    def caf(modal_dict):
        out = {}
        for mineral, pct in modal_dict.items():
            if mineral in chem_indexed.index:
                for el in XRF_ELEMENTS:
                    val = chem_indexed.loc[mineral, el]
                    frac = (float(val) if pd.notna(val) else 0.0) / 100.0
                    if frac > 0:
                        out[el] = out.get(el, 0.0) + pct * frac
        return {el: round(v, 3) for el, v in out.items()}

    assays = caf(modal)
    lib = LiberationState(degree={m: liberation_deg for m in modal})
    feed = Stream(name="minerai_custom", solids_tph=feed_tph, modal=modal,
                  liberation=lib, p80_um=p80, assays=assays)
    return feed, prop_lookup, caf


# ============================ LANCEMENT : stockage en session ============================
if lancer:
    feed, prop_lookup, assay_func = build_feed()
    st.session_state["feed"] = feed
    st.session_state["prop_lookup"] = prop_lookup
    st.session_state["assay_func"] = assay_func
    st.session_state["element"] = element
    st.session_state["traitement"] = traitement
    st.session_state["has_result"] = True
    if traitement == "Separation simple":
        st.session_state["unit_type"] = unit_type
        st.session_state["settings"] = dict(settings)
    else:
        st.session_state["stage_configs"] = editor_to_stage_configs(circuit_editor)


# ============================ AFFICHAGE DES RESULTATS ============================
if st.session_state.get("has_result"):
    feed = st.session_state["feed"]
    prop_lookup = st.session_state["prop_lookup"]
    assay_func = st.session_state["assay_func"]
    element = st.session_state["element"]
    traitement = st.session_state["traitement"]

    st.header("Resultats")
    st.subheader("Mineralogie de l'alimentation (%)")
    st.dataframe([{"Mineral": m, "%": round(v, 2)} for m, v in feed.modal.items()],
                 use_container_width=True)

    if traitement == "Separation simple":
        unit_type = st.session_state["unit_type"]
        settings = st.session_state["settings"]
        unit = SeparationUnit(unit_type, settings)
        conc, rejet = apply_unit_ui(feed, unit, prop_lookup=prop_lookup, assay_func=assay_func)

        st.subheader(f"Performance (metal suivi : {element})")
        perf_table(feed, [("Concentre", conc), ("Rejet", rejet)], element)

        # ---- Section courbe ----
        st.markdown("---")
        st.subheader("Courbe teneur-recuperation")
        st.caption("Coherente avec la separation ci-dessus : on balaye un parametre "
                   "autour du point simule, tout le reste etant fixe.")
        params = SWEEP_PARAMS.get(unit_type, [])
        if not params:
            st.info("Aucun parametre continu a balayer pour cette voie.")
        else:
            csweep = st.selectbox("Parametre a balayer", options=params, key="sweep_simple")
            rule = SEPARATION_SPECS[unit_type].get(csweep, {})
            vmin = float(rule.get("min", 0.0))
            vmax = float(rule.get("max", 1.0))
            c1, c2 = st.columns(2)
            lo = c1.number_input("Min", value=vmin, key="lo_s")
            hi = c2.number_input("Max", value=vmax, key="hi_s")
            if st.button("Tracer la courbe", key="trace_simple"):
                pts = grade_recovery_simple(
                    feed, unit_type, settings, csweep, np.linspace(lo, hi, 12),
                    element, prop_lookup=prop_lookup, assay_func=assay_func)
                plot_grade_recovery(pts, element, csweep,
                                    f"Teneur-recuperation ({element}) - balayage {csweep}")
# ---- Section cinetique (flottation uniquement) ----
        if unit_type == "flotation":
            st.markdown("---")
            st.subheader("Cinetique de flottation")
            st.caption("Recuperation de chaque mineral en fonction du temps de residence, "
                       "a reglages fixes. On voit la selectivite s'installer dans le temps : "
                       "les mineraux flottables montent vite vers leur plateau.")
            if st.button("Tracer la cinetique", key="trace_kinetics"):
                unit_k = SeparationUnit(unit_type, settings)
                curves = kinetics_curve(feed, unit_k, mineral_props=prop_lookup)

                fig, ax = plt.subplots(figsize=(7, 5))
                for mineral, (times, recs) in curves.items():
                    ax.plot(times, recs, "-", lw=2, label=mineral)
                ax.set_xlabel("Temps de residence (min)")
                ax.set_ylabel("Recuperation (%)")
                ax.set_title("Cinetique de flottation par mineral")
                ax.grid(True, alpha=0.3)
                ax.legend(fontsize=8)
                ax.set_ylim(0, 100)
                fig.tight_layout()
                st.pyplot(fig)
                st.caption("Le temps de residence actuel du reglage est "
                           f"{settings.get('residence_min', 0):.1f} min. Au-dela du plateau "
                           "d'un mineral, prolonger ne fait qu'entrainer de la gangue.")
    else:  # Circuit
        stage_configs = st.session_state["stage_configs"]
        if len(stage_configs) == 0:
            st.error("Definissez au moins un etage (avec un nom).")
            st.stop()
        result = run_differential_circuit(feed, stage_configs,
                                          prop_lookup=prop_lookup, assay_func=assay_func)
        concentrates = result["concentrates"]
        tail = result["final_tail"]

        st.subheader(f"Performance (metal suivi : {element})")
        streams_named = [(f"Conc. {name}", c) for name, c in concentrates.items()]
        streams_named.append(("Rejet final", tail))
        perf_table(feed, streams_named, element)

        # ---- Section courbe ----
        st.markdown("---")
        st.subheader("Courbe teneur-recuperation")
        st.caption("Choisissez le concentre a suivre et le parametre d'un etage a balayer. "
                   "Le circuit entier est re-simule a chaque point.")
        conc_names = list(concentrates.keys())
        stage_names = [c["name"] for c in stage_configs]
        c1, c2, c3 = st.columns(3)
        target_conc = c1.selectbox("Concentre suivi", options=conc_names, key="tc")
        stage_lbl = c2.selectbox("Etage a regler", options=stage_names, key="stg")
        sweep_p = c3.selectbox("Parametre", options=["pulp_ph", "collector_gpt"], key="sp")
        stage_index = stage_names.index(stage_lbl)
        d1, d2 = st.columns(2)
        default_min = 7.0 if sweep_p == "pulp_ph" else 20.0
        default_max = 11.5 if sweep_p == "pulp_ph" else 300.0
        lo = d1.number_input("Min", value=default_min, key="lo_c")
        hi = d2.number_input("Max", value=default_max, key="hi_c")
        if st.button("Tracer la courbe", key="trace_circuit"):
            pts = grade_recovery_circuit(
                feed, stage_configs, stage_index, sweep_p, np.linspace(lo, hi, 12),
                element, target_conc, prop_lookup=prop_lookup, assay_func=assay_func)
            plot_grade_recovery(
                pts, element, sweep_p,
                f"Teneur-recuperation ({element}) dans conc. {target_conc} "
                f"- balayage {sweep_p} etage {stage_lbl}")
else:
    if not use_custom_minerals and traitement != "Circuit":
        st.info("Configurez le minerai et le traitement dans la barre laterale, "
                "puis cliquez sur **Lancer**.")