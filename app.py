"""
app.py
Interface web du simulateur geometallurgique (Streamlit), multilingue FR/EN.

Un selecteur de langue en haut de la barre laterale bascule tous les textes via i18n.t().
Onglet unique : minerai (profil / base / mineraux custom), separation simple ou circuit,
tableau de performance (recuperations massique et metallurgique), puis courbes teneur-
recuperation et cinetique de flottation, coherentes avec le point simule.

L'interface habille la logique de src/ (principe logique/presentation separe).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

from i18n import t, LANGUAGES, param_label, option_label, route_label
from feed_generator import generate_feed, apply_p80, liberation_from_p80
from mineralogy import ORE_PROFILES, MINERALS, assays_from_modal
from data_models import Stream, LiberationState
from separation import SeparationUnit, SEPARATION_SPECS, separate
from laws_gravity import gravity_recovery, gravity_cutpoint, gold_gravity_recovery
from laws_magnetic import magnetic_recovery, magnetic_cutpoint
from laws_flotation import flotation_recovery, gold_flotation_recovery
from circuit_cu_zn import run_differential_circuit
from geomet_curves import (performance_row, grade_recovery_simple,
                           grade_recovery_circuit, kinetics_curve)


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

SWEEP_PARAMS = {
    "shaking_table": ["deck_slope_deg", "wash_water_lpm", "feed_rate_tph"],
    "spiral": ["wash_water_lpm", "feed_rate_tph"],
    "falcon": ["g_force", "fluidization_lpm"],
    "magnetic": ["field_tesla", "drum_speed_rpm"],
    "flotation": ["collector_gpt", "pulp_ph", "residence_min"],
}
GRAVITY_ROUTES = ("shaking_table", "spiral", "falcon")

st.set_page_config(page_title="Simulateur geometallurgique", layout="wide")

# ----- Selecteur de langue, tout en haut de la sidebar, car il pilote tous les textes :
# ainsi on lit la langue avant d'afficher quoi que ce soit d'autre. -----
lang_label = st.sidebar.selectbox("Language / Langue", options=list(LANGUAGES.keys()))
lang = LANGUAGES[lang_label]

st.title(t("app_title", lang))
st.caption(t("app_caption", lang))
# Grille granulometrique active du flowsheet, car l'utilisateur peut la redefinir : ainsi
# toutes les PSD sont generees sur SA grille (initialisee a la grille par defaut).
from size_classes import DEFAULT_GRID_UM
if "grid" not in st.session_state:
    st.session_state["grid"] = list(DEFAULT_GRID_UM)

# ============================ FONCTIONS PARTAGEES ============================
def apply_unit_ui(stream, unit, prop_lookup=None, assay_func=None,
                  direct_d50=None, direct_ep=None):
    if unit.unit_type in ("shaking_table", "spiral", "falcon"):
        # Coupure imposee si fournie, sinon calculee depuis les reglages machine.
        if direct_d50 is not None:
            d50, ep = direct_d50, direct_ep
        else:
            d50, ep = gravity_cutpoint(unit)
        reco = gravity_recovery(stream, d50, ep, densities=prop_lookup)
        au = gold_gravity_recovery(stream, reco, unit, d50=d50, ep=ep)
        return separate(stream, reco, gold_recovery=au, assay_func=assay_func)
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
    rows = []
    for name, s in streams_named:
        r = performance_row(feed, s, element)
        rows.append({t("product", lang): name, **r})
    st.dataframe(rows, use_container_width=True)


def plot_grade_recovery(points, element, sweep_param, title, sweep_label=None):
    reco = [p["recup_metal_%"] for p in points]
    grade = [p["teneur_%"] for p in points]
    vals = [p["param"] for p in points]

    amp_reco = max(reco) - min(reco) if reco else 0.0
    amp_grade = max(grade) - min(grade) if grade else 0.0
    mean_reco = (sum(reco) / len(reco)) if reco else 1.0
    mean_grade = (sum(grade) / len(grade)) if grade else 1.0
    rel_reco = amp_reco / mean_reco if mean_reco > 1e-9 else 0.0
    rel_grade = amp_grade / mean_grade if mean_grade > 1e-9 else 0.0
    if rel_reco < 0.005 and rel_grade < 0.005:
        st.warning(t("flat_warning", lang, el=element, p=sweep_param,
                     ar=amp_reco, ag=amp_grade))

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(reco, grade, "o-", color="#C62828", lw=2, markersize=6)
    for r, g, v in zip(reco, grade, vals):
        ax.annotate(f"{v:.1f}", (r, g), fontsize=7, alpha=0.6,
                    textcoords="offset points", xytext=(4, 4))
    ax.set_xlabel(t("recovery_axis", lang, el=element))
    grade_unit = "g/t" if element == "Au" else "%"
    ax.set_ylabel(f"{t('grade_axis', lang, el=element)}".replace("(%)", f"({grade_unit})"))
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig)

    st.subheader(t("curve_points", lang))
    col_param = sweep_label if sweep_label else sweep_param
    st.dataframe([{col_param: p["param"], t("col_recov", lang): p["recup_metal_%"],
                   t("col_grade", lang): p["teneur_%"], t("col_mass", lang): p["recup_massique_%"]}
                  for p in points], use_container_width=True)

def plot_psd(grid, psd, p80, mode, lang):
    """Trace la PSD, car l'utilisateur doit VOIR la granulometrie : en mode 'freq' un
    histogramme (masse par classe, ou est la matiere), en mode 'cum' la courbe de passant
    cumule (representation standard ou l'on lit le P80)."""
    from size_classes import class_labels, class_representative_sizes
    labels = class_labels(grid)
    fig, ax = plt.subplots(figsize=(7, 5))
    if mode == "cum":
        # Passant cumule : somme des classes plus fines, en fonction de la taille.
        # On construit (taille de borne, passant sous cette borne).
        sizes = list(grid)
        passing = [sum(psd[i + 1:]) * 100.0 for i in range(len(grid))]
        # Trie par taille croissante pour une courbe lisible.
        pairs = sorted(zip(sizes, passing))
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        ax.plot(xs, ys, "o-", color="#c0392b", linewidth=2)
        ax.axhline(80, color="gray", linestyle="--", linewidth=1)
        ax.axvline(p80, color="gray", linestyle="--", linewidth=1)
        ax.set_xscale("log")
        ax.set_xlabel(t("psd_size_axis", lang))
        ax.set_ylabel(t("psd_passing_axis", lang))
        ax.set_title(t("psd_cum_title", lang, p80=p80))
    else:
        # Histogramme frequentiel : % de masse par classe.
        pct = [x * 100.0 for x in psd]
        ax.bar(range(len(labels)), pct, color="#c0392b")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_xlabel(t("psd_class_axis", lang))
        ax.set_ylabel(t("psd_massfrac_axis", lang))
        ax.set_title(t("psd_freq_title", lang, p80=p80))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=False)
# ============================ SIDEBAR : MINERAI ============================
st.sidebar.header(t("ore_header", lang))
feed_tph = st.sidebar.number_input(t("feed_rate", lang),
                                   min_value=1.0, max_value=10000.0, value=100.0, step=10.0)
mode_minerai = st.sidebar.radio(
    t("mode", lang),
    [t("mode_profile", lang), t("mode_base", lang), t("mode_custom", lang)])

profile_name = None
custom_modal = None
use_custom_minerals = False

if mode_minerai == t("mode_profile", lang):
    profile_name = st.sidebar.selectbox(t("profile", lang), options=list(ORE_PROFILES.keys()))
elif mode_minerai == t("mode_base", lang):
    st.sidebar.markdown("**" + t("compose_base", lang) + "**")
    custom_modal = {}
    for mineral in MINERALS.keys():
        pct = st.sidebar.slider(mineral, 0.0, 100.0, 0.0, step=0.5)
        if pct > 0:
            custom_modal[mineral] = pct
    total_saisi = sum(custom_modal.values())
    if total_saisi == 0:
        st.sidebar.warning(t("add_phase_warn", lang))
    elif abs(total_saisi - 100.0) < 0.01:
        st.sidebar.success(t("total_ok", lang, v=total_saisi))
    else:
        st.sidebar.info(t("total_renorm", lang, v=total_saisi))
else:
    use_custom_minerals = True
    st.sidebar.markdown("**" + t("custom_minerals_label", lang) + "**")
    st.sidebar.caption(t("custom_minerals_caption", lang))

p80 = st.sidebar.slider(t("p80", lang), 10.0, 300.0, 150.0, step=5.0)

# ============================ SIDEBAR : METAL D'INTERET ============================
st.sidebar.header(t("metal_header", lang))
element = st.sidebar.selectbox(
    t("metal_followed", lang),
    options=["Fe", "Cu", "Zn", "Pb", "SiO2", "Au", "Ag", "Sn", "Ni", "Co", "As", "S"])

# ============================ SIDEBAR : TRAITEMENT ============================
st.sidebar.header(t("process_header", lang))
traitement = st.sidebar.radio(t("process_type", lang),
                              [t("process_simple", lang), t("process_circuit", lang),
                               t("process_multi", lang)])
is_circuit = (traitement == t("process_circuit", lang))
is_multi = (traitement == t("process_multi", lang))

unit_type = None
settings = {}
template_name = None

if not is_circuit and not is_multi:
    st.sidebar.subheader(t("sep_route", lang))
    voies = ["shaking_table", "spiral", "falcon", "magnetic", "flotation"]
    display_voies = [route_label(v, lang) for v in voies]
    picked_voie = st.sidebar.selectbox(t("unit_type", lang), options=display_voies)
    unit_type = voies[display_voies.index(picked_voie)]
    st.sidebar.subheader(t("machine_settings", lang))
    cut_mode = "machine"   # par defaut : reglages machine
    direct_d50 = None
    direct_ep = None
    if unit_type in GRAVITY_ROUTES:
        # Choix du mode de reglage, car un concentrateur gravimetrique peut se piloter par
        # ses reglages machine OU par une coupure imposee : ainsi l'utilisateur choisit.
        cut_mode_label = st.sidebar.radio(
            t("cut_mode", lang),
            [t("cut_mode_machine", lang), t("cut_mode_direct", lang)])
        cut_mode = "direct" if cut_mode_label == t("cut_mode_direct", lang) else "machine"

    if cut_mode == "direct":
        # Coupure imposee : l'utilisateur fixe d50 (densite de partage) et Ep (nettete).
        direct_d50 = st.sidebar.slider(t("d50_label", lang), 1.5, 20.0, 5.0, step=0.1)
        direct_ep = st.sidebar.slider(t("ep_label", lang), 0.05, 1.0, 0.35, step=0.05)
    else:
        for param, rule in SEPARATION_SPECS[unit_type].items():
            if param.startswith("_"):
                continue
            label = param_label(param, lang)
            if "choices" in rule:
                choices = rule["choices"]
                display = [option_label(c, lang) for c in choices]
                idx = choices.index(rule["default"])
                picked = st.sidebar.selectbox(label, options=display, index=idx)
                settings[param] = choices[display.index(picked)]
            elif "min" in rule:
                settings[param] = st.sidebar.slider(
                    label, float(rule["min"]), float(rule["max"]), float(rule["default"]))
else:
    st.sidebar.subheader(t("circuit_composed", lang))
    template_name = st.sidebar.selectbox(t("start_from_template", lang),
                                         options=list(CIRCUIT_TEMPLATES.keys()))
    st.sidebar.caption(t("circuit_edit_hint", lang))

lancer = st.sidebar.button(t("run", lang), type="primary")


# ============================ ZONE PRINCIPALE : SAISIE ============================
custom_props = None
custom_chem = None
# ---- Grille granulometrique (commune a tout le flowsheet) ----
with st.expander(t("grid_section", lang), expanded=False):
    st.caption(t("grid_caption", lang))
    grid_df = pd.DataFrame({"borne_um": st.session_state["grid"]})
    grid_edited = st.data_editor(grid_df, num_rows="dynamic",
                                 use_container_width=True, key="grid_editor")
    try:
        new_grid = sorted([float(x) for x in grid_edited["borne_um"].dropna()
                           if float(x) > 0], reverse=True)
        if len(new_grid) >= 2:
            st.session_state["grid"] = new_grid
        else:
            st.warning(t("grid_min_warning", lang))
    except (ValueError, TypeError):
        st.warning(t("grid_invalid_warning", lang))
if use_custom_minerals:
    st.header(t("custom_def_header", lang))
    st.markdown("**" + t("table1_props", lang) + "**")
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
    st.markdown("**" + t("table2_chem", lang) + "**")
    minerals_list = [m for m in custom_props["mineral"].tolist() if str(m).strip()]
    chem_init = pd.DataFrame({"mineral": minerals_list})
    for el in XRF_ELEMENTS:
        chem_init[el] = 0.0
    custom_chem = st.data_editor(chem_init, use_container_width=True, key="chem_editor")

circuit_editor = None
if is_circuit:
    st.header(t("circuit_compo_header", lang))
    st.markdown(t("circuit_compo_hint", lang))
    st.caption(t("base_minerals", lang) + ", ".join(MINERALS.keys()))
    circuit_editor = st.data_editor(
        CIRCUIT_TEMPLATES[template_name], num_rows="dynamic",
        use_container_width=True, key="circuit_editor")
# ---- Composition d'un circuit multi-voies (etages heterogenes) ----
multi_stages = []
if is_multi:
    st.header(t("process_multi", lang))
    st.caption("Composez un circuit ou chaque etage peut etre d'une voie differente "
               "(gravite, magnetique, flottation). Le rejet d'un etage alimente le suivant.")
    n_stages = st.number_input(t("n_stages", lang), min_value=1, max_value=6, value=2, step=1)
    voies_multi = ["shaking_table", "spiral", "falcon", "magnetic", "flotation", "ball_mill", "hydrocyclone"]

    for i in range(int(n_stages)):
        with st.expander(f"{t('stage_n', lang)} {i+1}", expanded=(i == 0)):
            name = st.text_input(t("stage_name", lang), value=f"etage_{i+1}",
                                 key=f"ms_name_{i}")
            voie_disp = [route_label(v, lang) for v in voies_multi]
            picked = st.selectbox(t("stage_route", lang), options=voie_disp, key=f"ms_route_{i}")
            unit_type_i = voies_multi[voie_disp.index(picked)]
            # Metal d'interet propre a cet etage, car chaque etage vise souvent un metal
            # different (Cu dans l'etage Cu, Fe dans l'etage magnetique...) : ainsi le suivi
            # se fait par etage.
            metals = ["Fe", "Cu", "Zn", "Pb", "SiO2", "Au", "Ag", "Sn", "Ni", "Co", "As", "S"]
            metal_i = st.selectbox(t("metal_followed", lang), options=metals, key=f"ms_metal_{i}")
            # Reglages de la voie choisie, generes depuis SEPARATION_SPECS.
            settings_i = {}
            for param, rule in SEPARATION_SPECS[unit_type_i].items():
                if param.startswith("_"):
                    continue
                label = param_label(param, lang)
                if "choices" in rule:
                    choices = rule["choices"]
                    disp = [option_label(c, lang) for c in choices]
                    idx = choices.index(rule["default"])
                    pick = st.selectbox(label, options=disp, index=idx, key=f"ms_{i}_{param}")
                    settings_i[param] = choices[disp.index(pick)]
                elif "min" in rule:
                    settings_i[param] = st.slider(
                        label, float(rule["min"]), float(rule["max"]),
                        float(rule["default"]), key=f"ms_{i}_{param}")
            multi_stages.append({"name": name, "unit_type": unit_type_i, "settings": settings_i, "metal": metal_i})
# ---- Retours (charge circulante) ----
    st.subheader(t("returns_section", lang))
    st.caption(t("returns_caption", lang))
    from flowsheet import outputs_of
    stage_names_multi = [s["name"] for s in multi_stages]
    multi_returns = []
    if len(multi_stages) >= 2:
        n_returns = st.number_input(t("n_returns", lang), min_value=0, max_value=3,
                                    value=0, step=1)
        for r in range(int(n_returns)):
            st.markdown(f"**{t('return_n', lang)} {r+1}**")
            rc1, rc2, rc3 = st.columns(3)
            # Etage source
            src_stage = rc1.selectbox(t("return_from_stage", lang), options=stage_names_multi,
                                      key=f"ret_src_{r}")
            # Sortie de l'etage source (depend de son type)
            src_unit_type = next(s["unit_type"] for s in multi_stages if s["name"] == src_stage)
            src_outs = outputs_of(src_unit_type)
            src_out = rc2.selectbox(t("return_output", lang),
                                    options=[option_label(o, lang) if o in ("overflow", "underflow") else o for o in src_outs],
                                    key=f"ret_out_{r}")
            # Retrouver la cle technique de la sortie choisie
            src_out_key = src_outs[[option_label(o, lang) if o in ("overflow", "underflow") else o for o in src_outs].index(src_out)]
            # Etage destination
            dst_stage = rc3.selectbox(t("return_to_stage", lang), options=stage_names_multi,
                                      key=f"ret_dst_{r}")
            multi_returns.append({"from_stage": src_stage, "from_output": src_out_key,
                                  "to_stage": dst_stage})
    else:
        st.info(t("returns_need_two", lang))

def plot_partition_curve(grid, d50, sharpness, lang):
    """Trace la courbe de partage (Tromp) d'un hydrocyclone, car c'est sa signature : ainsi
    on montre, pour chaque taille, la probabilite d'aller a la sousverse (grossiers), avec
    le d50 (taille de coupure a 50%) marque."""
    from size_classes import class_representative_sizes
    from classification import cyclone_partition
    sizes = class_representative_sizes(grid)
    # Courbe lisse sur une plage de tailles (pas seulement les classes).
    xs = np.logspace(np.log10(min(sizes) * 0.5), np.log10(max(sizes) * 1.5), 100)
    ys = [cyclone_partition(x, d50, sharpness) * 100.0 for x in xs]
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(xs, ys, "-", color="#c0392b", linewidth=2)
    ax.axhline(50, color="gray", linestyle="--", linewidth=1)
    ax.axvline(d50, color="gray", linestyle="--", linewidth=1)
    ax.annotate(f"d50 = {d50:.0f} um", (d50, 50), fontsize=8,
                textcoords="offset points", xytext=(6, 6))
    ax.set_xscale("log")
    ax.set_xlabel(t("partition_size_axis", lang))
    ax.set_ylabel(t("partition_yaxis", lang))
    ax.set_title(t("partition_title", lang))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=False)

def build_feed():
    prop_lookup = None
    assay_func = None
    if profile_name is not None:
        feed = generate_feed(profile_name, n_samples=1, seed=42, feed_tph=feed_tph, grid=st.session_state["grid"])[0]
        # Recalcule liberation ET distribution de l'or selon le P80 choisi, car le curseur
        # doit reellement piloter la recuperation : ainsi le P80 de la sidebar devient actif.
        apply_p80(feed, p80)
        return feed, prop_lookup, assay_func
    if custom_modal is not None:
        total = sum(custom_modal.values())
        if total == 0:
            st.error(t("err_add_phase", lang))
            st.stop()
        modal = {m: round(v / total * 100, 3) for m, v in custom_modal.items()}
        assays = assays_from_modal(modal)
        lib = LiberationState(degree={m: liberation_from_p80(p80) for m in modal})
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
        st.error(t("err_define_mineral", lang))
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
    lib = LiberationState(degree={m: liberation_from_p80(p80) for m in modal})
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
    st.session_state["is_circuit"] = is_circuit
    st.session_state["is_multi"] = is_multi
    st.session_state["has_result"] = True
    if is_multi:
        st.session_state["multi_stages"] = multi_stages
        st.session_state["multi_returns"] = multi_returns
    elif is_circuit:
        st.session_state["stage_configs"] = editor_to_stage_configs(circuit_editor)
    else:
        st.session_state["unit_type"] = unit_type
        st.session_state["settings"] = dict(settings)


# ============================ AFFICHAGE DES RESULTATS ============================
if st.session_state.get("has_result"):
    feed = st.session_state["feed"]
    prop_lookup = st.session_state["prop_lookup"]
    assay_func = st.session_state["assay_func"]
    element = st.session_state["element"]
    res_is_circuit = st.session_state["is_circuit"]
    res_is_multi = st.session_state.get("is_multi", False)
    st.header(t("results", lang))
    st.subheader(t("feed_mineralogy", lang))
    st.dataframe([{t("mineral", lang): m, "%": round(v, 2)} for m, v in feed.modal.items()],
                 use_container_width=True)
# Granulometrie de l'alimentation, car la PSD est desormais une donnee de premier plan :
    # ainsi l'utilisateur voit la distribution et le P80 qui en derive.
    if feed.psd_curve is not None:
        st.subheader(t("psd_section", lang))
        from size_classes import DEFAULT_GRID_UM, class_labels
        grid = st.session_state["grid"]
        labels = class_labels(grid)
        view = st.radio(t("psd_view", lang),
                        [t("psd_view_freq", lang), t("psd_view_cum", lang)],
                        horizontal=True, key="psd_view_feed")
        mode = "cum" if view == t("psd_view_cum", lang) else "freq"
        plot_psd(grid, feed.psd_curve, feed.p80_um, mode, lang)
    if res_is_multi:
        # Circuit multi-voies : execution via le moteur GRAPHE (gere serie ET boucles).
        from flowsheet import run_series_as_graph
        stages = st.session_state["multi_stages"]
        returns = st.session_state.get("multi_returns", [])
        result = run_series_as_graph(feed, stages, prop_lookup=prop_lookup,
                                     assay_func=assay_func, grid=st.session_state["grid"],
                                     apply_p80_func=apply_p80, returns=returns)
        concentrates = result["concentrates"]
        tail = result["final_tail"]
        stage_feeds = result["stage_feeds"]
        circ = result["circulating"]
        # Affichage de la charge circulante si boucle(s).
        if circ["n_tears"] > 0:
            if circ["status"] == "converged":
                st.success(t("cc_converged", lang, n=circ["n_iter"],
                             load=round(sum(circ["tear_debits"]), 1)))
            elif circ["status"] == "diverged":
                st.error(t("cc_diverged", lang))
            elif circ["status"] == "circulating_load_too_high":
                st.error(t("cc_too_high", lang))
            else:
                st.warning(t("cc_max_iter", lang, n=circ["n_iter"]))

        # Un bloc de resultats par etage, car chaque etage a sa voie et son metal suivi :
        # ainsi on lit la performance de chaque etage sur SON metal d'interet.
        mill_outputs = result.get("mill_outputs", {})
        for s in stages:
            name = s["name"]
            metal_i = s.get("metal", element)
            # Cas broyeur : pas de concentre, mais on montre l'effet du broyage (P80 avant/apres).
            if s["unit_type"] == "ball_mill":
                st.markdown(f"### {t('stage_n', lang)} : {name} "
                            f"({route_label('ball_mill', lang)})")
                feed_in = stage_feeds.get(name)
                ground = mill_outputs.get(name)
                if feed_in is not None and ground is not None:
                    st.write(t("mill_result", lang,
                               p_in=round(feed_in.p80_um, 1),
                               p_out=round(ground.p80_um, 1),
                               e=s["settings"].get("energy_kwht", 0),
                               wi=s["settings"].get("work_index", 0)))
                    # Granulometrie apres broyage
                    view_m = st.radio(t("psd_view", lang),
                                      [t("psd_view_freq", lang), t("psd_view_cum", lang)],
                                      horizontal=True, key=f"psdview_mill_{name}")
                    mode_m = "cum" if view_m == t("psd_view_cum", lang) else "freq"
                    plot_psd(st.session_state["grid"], ground.psd_curve, ground.p80_um, mode_m, lang)
                st.markdown("---")
                continue
            # Cas hydrocyclone : deux flux (overflow fin, underflow grossier).
            if s["unit_type"] == "hydrocyclone":
                st.markdown(f"### {t('stage_n', lang)} : {name} "
                            f"({route_label('hydrocyclone', lang)})")
                cyc = result.get("cyclone_outputs", {}).get(name)
                if cyc is not None:
                    over, under = cyc["overflow"], cyc["underflow"]
                    st.write(t("cyclone_result", lang,
                               m_over=round(over.solids_tph, 1), p_over=round(over.p80_um, 1),
                               m_under=round(under.solids_tph, 1), p_under=round(under.p80_um, 1),
                               cont=option_label(s["settings"].get("continue_flux", "overflow"), lang)))
                    # Courbe de partage (Tromp), signature de l'hydrocyclone.
                    from classification import cyclone_cutpoint
                    d50_cyc, sharp_cyc = cyclone_cutpoint(
                        s["settings"].get("diameter_cm", 15.0),
                        s["settings"].get("pressure_kpa", 100.0))
                    plot_partition_curve(st.session_state["grid"], d50_cyc, sharp_cyc, lang)
                st.markdown("---")
                continue
            conc = concentrates.get(name)
            if conc is None:
                continue
            st.markdown(f"### {t('stage_n', lang)} : {name} "
                        f"({route_label(s['unit_type'], lang)})")
            perf_table(feed, [(f"{t('concentrate', lang)} {name}", conc)], metal_i)
# Courbe locale de l'etage, car on veut le compromis teneur-recuperation de CET
            # etage sur le flux qu'il recoit : ainsi on balaye un parametre de l'etage sur
            # son alimentation reelle (rejet de l'etage precedent).
            stage_feed = stage_feeds.get(name, feed)
            params_i = SWEEP_PARAMS.get(s["unit_type"], [])
            if params_i:
                disp_i = [param_label(p, lang) for p in params_i]
                pick_i = st.selectbox(t("sweep_param", lang), options=disp_i,
                                      key=f"msweep_{name}")
                csweep_i = params_i[disp_i.index(pick_i)]
                rule_i = SEPARATION_SPECS[s["unit_type"]].get(csweep_i, {})
                vmin_i = float(rule_i.get("min", 0.0))
                vmax_i = float(rule_i.get("max", 1.0))
                cc1, cc2 = st.columns(2)
                lo_i = cc1.number_input(t("min_val", lang), value=vmin_i, key=f"mlo_{name}_{csweep_i}")
                hi_i = cc2.number_input(t("max_val", lang), value=vmax_i, key=f"mhi_{name}_{csweep_i}")
                # Persistance : un clic MEMORISE la demande de courbe pour cet etage, car
                # Streamlit reexecute tout le script a chaque clic : ainsi les courbes des
                # autres etages ne disparaissent plus (on les reaffiche depuis la session).
                if st.button(t("trace_curve", lang), key=f"mtrace_{name}"):
                    st.session_state[f"curve_{name}"] = {
                        "sweep": csweep_i, "lo": lo_i, "hi": hi_i, "metal": metal_i}
                curve_req = st.session_state.get(f"curve_{name}")
                if curve_req is not None:
                    pts_i = grade_recovery_simple(
                        stage_feed, s["unit_type"], s["settings"], curve_req["sweep"],
                        np.linspace(curve_req["lo"], curve_req["hi"], 12), curve_req["metal"],
                        prop_lookup=prop_lookup, assay_func=assay_func)
                    plot_grade_recovery(pts_i, curve_req["metal"], curve_req["sweep"],
                                        t("gr_title_simple", lang, el=curve_req["metal"],
                                          p=param_label(curve_req["sweep"], lang)),
                                        sweep_label=param_label(curve_req["sweep"], lang))
            st.markdown("---")
        st.markdown(f"### {t('final_tail', lang)}")
        perf_table(feed, [(t("final_tail", lang), tail)], element)
        total_out = sum(c.solids_tph for c in concentrates.values()) + tail.solids_tph
        st.caption(f"Conservation masse : {total_out:.1f} t/h (alim {feed.solids_tph:.0f} t/h)")
    elif not res_is_circuit:
        unit_type = st.session_state["unit_type"]
        settings = st.session_state["settings"]
        unit = SeparationUnit(unit_type, settings)
        conc, rejet = apply_unit_ui(feed, unit, prop_lookup=prop_lookup, assay_func=assay_func,
                                    direct_d50=st.session_state.get("direct_d50"),
                                    direct_ep=st.session_state.get("direct_ep"))

        st.subheader(t("performance", lang, el=element))
        perf_table(feed, [(t("concentrate", lang), conc), (t("tailings", lang), rejet)], element)

        st.markdown("---")
        st.subheader(t("gr_curve_title", lang))
        st.caption(t("gr_curve_simple_caption", lang))
        params = SWEEP_PARAMS.get(unit_type, [])
        if not params:
            st.info(t("no_sweep_param", lang))
        else:
           # On affiche les libelles traduits mais 'csweep' reste la cle technique, car
            # SEPARATION_SPECS et la fonction de courbe l'attendent : ainsi on traduit a
            # l'affichage seulement.
            csweep_display = [param_label(p, lang) for p in params]
            csweep_picked = st.selectbox(t("sweep_param", lang), options=csweep_display,
                                         key="sweep_simple")
            csweep = params[csweep_display.index(csweep_picked)]
            rule = SEPARATION_SPECS[unit_type].get(csweep, {})
            vmin = float(rule.get("min", 0.0))
            vmax = float(rule.get("max", 1.0))
            c1, c2 = st.columns(2)
            lo = c1.number_input(t("min_val", lang), value=vmin, key=f"lo_s_{csweep}")
            hi = c2.number_input(t("max_val", lang), value=vmax, key=f"hi_s_{csweep}")
            if st.button(t("trace_curve", lang), key="trace_simple"):
                pts = grade_recovery_simple(
                    feed, unit_type, settings, csweep, np.linspace(lo, hi, 12),
                    element, prop_lookup=prop_lookup, assay_func=assay_func)
                plot_grade_recovery(pts, element, csweep,
                                    t("gr_title_simple", lang, el=element, p=param_label(csweep, lang)),
                                    sweep_label=param_label(csweep, lang))

        if unit_type == "flotation":
            st.markdown("---")
            st.subheader(t("kinetics_title", lang))
            st.caption(t("kinetics_caption", lang))
            if st.button(t("trace_kinetics", lang), key="trace_kinetics"):
                unit_k = SeparationUnit(unit_type, settings)
                curves = kinetics_curve(feed, unit_k, mineral_props=prop_lookup)
                fig, ax = plt.subplots(figsize=(7, 5))
                for mineral, (times, recs) in curves.items():
                    ax.plot(times, recs, "-", lw=2, label=mineral)
                ax.set_xlabel(t("time_axis", lang))
                ax.set_ylabel(t("recovery_pct", lang))
                ax.set_title(t("kinetics_plot_title", lang))
                ax.grid(True, alpha=0.3)
                ax.legend(fontsize=8)
                ax.set_ylim(0, 100)
                fig.tight_layout()
                st.pyplot(fig)
                st.caption(t("kinetics_foot", lang, t=settings.get("residence_min", 0)))

    else:  # Circuit
        stage_configs = st.session_state["stage_configs"]
        if len(stage_configs) == 0:
            st.error(t("define_stage_err", lang))
            st.stop()
        result = run_differential_circuit(feed, stage_configs,
                                          prop_lookup=prop_lookup, assay_func=assay_func)
        concentrates = result["concentrates"]
        tail = result["final_tail"]

        st.subheader(t("performance", lang, el=element))
        streams_named = [(f"{t('concentrate', lang)} {name}", c) for name, c in concentrates.items()]
        streams_named.append((t("final_tail", lang), tail))
        perf_table(feed, streams_named, element)

        st.markdown("---")
        st.subheader(t("gr_curve_title", lang))
        st.caption(t("gr_curve_circuit_caption", lang))
        conc_names = list(concentrates.keys())
        stage_names = [c["name"] for c in stage_configs]
        c1, c2, c3 = st.columns(3)
        target_conc = c1.selectbox(t("tracked_conc", lang), options=conc_names, key="tc")
        stage_lbl = c2.selectbox(t("stage_to_set", lang), options=stage_names, key="stg")
        # Libelles traduits, cle technique conservee pour le calcul.
        sweep_p_keys = ["pulp_ph", "collector_gpt"]
        sweep_p_display = [param_label(k, lang) for k in sweep_p_keys]
        sweep_p_picked = c3.selectbox(t("parameter", lang), options=sweep_p_display, key="sp")
        sweep_p = sweep_p_keys[sweep_p_display.index(sweep_p_picked)]
        stage_index = stage_names.index(stage_lbl)
        d1, d2 = st.columns(2)
        default_min = 7.0 if sweep_p == "pulp_ph" else 20.0
        default_max = 11.5 if sweep_p == "pulp_ph" else 300.0
        lo = d1.number_input(t("min_val", lang), value=default_min, key=f"lo_c_{sweep_p}")
        hi = d2.number_input(t("max_val", lang), value=default_max, key=f"hi_c_{sweep_p}")
        if st.button(t("trace_curve", lang), key="trace_circuit"):
            pts = grade_recovery_circuit(
                feed, stage_configs, stage_index, sweep_p, np.linspace(lo, hi, 12),
                element, target_conc, prop_lookup=prop_lookup, assay_func=assay_func)
            plot_grade_recovery(
                pts, element, sweep_p,
                t("gr_title_circuit", lang, el=element, c=target_conc, p=sweep_p, s=stage_lbl),
                sweep_label=param_label(sweep_p, lang))
else:
    if not use_custom_minerals and not is_circuit:
        st.info(t("info_configure", lang))
res_is_multi = st.session_state.get("is_multi", False)