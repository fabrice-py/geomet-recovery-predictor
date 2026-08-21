# Geometallurgical Flowsheet Simulator

A physics-based simulator for mineral processing flowsheets, written in Python with a
Streamlit interface. It predicts how an ore behaves through configurable separation,
comminution and classification circuits including closed circuits with circulating load,
solved by fixed-point iteration.

Every machine parameter has a real, physically-motivated effect on the result. This is not a
toy: it is designed to behave like a genuine process simulator, where changing a mill's
energy, a cyclone's pressure or a table's deck slope actually changes the outcome.

## Highlights

- **Multi-route circuits** : compose a flowsheet stage by stage, each stage using a different
  route (gravity, magnetic, flotation, comminution, classification), with per-stage settings
  and tracked metal.
- **Full particle size distribution (PSD)** : a real size distribution flows through the whole
  model. The grid of size classes is user-editable; the P80 is *derived* from the PSD.
- **Ball mill (Bond's law)** : a transformer unit that grinds a stream finer (reduced P80,
  improved liberation) as a function of specific energy and ore work index.
- **Hydrocyclone** : size classification into overflow (fines) and underflow (coarse), with a
  Tromp partition curve; the continuing stream is user-selectable.
- **Circulating load** : a graph-based flowsheet engine solves closed circuits (e.g. mill +
  cyclone in closed loop) by the tear-stream / fixed-point method, with convergence and
  divergence detection. Global mass is conserved at steady state.
- **Real characterization data** : load measured PSD, XRD (mineralogy), XRF (bulk chemistry,
  compared against the reconstructed chemistry), and SEM (measured liberation per mineral,
  overriding the P80-derived estimate). Manual entry and CSV import for each.
- **Bilingual UI** (French / English) with decoupled technical keys and display labels.
- **Automated tests** (pytest) covering mass conservation across separation, series circuits,
  cyclone and circulating load, plus physical invariants.

## What the simulator does

Starting from an ore, a predefined profile, a base-mineral composition, or a fully custom
mineralogy, the simulator builds a feed stream carrying mass, modal mineralogy, per-mode gold
distribution, liberation state and particle size distribution. That stream is then routed
through the flowsheet the user composes.

Each separation propagates mass, mineralogy, chemistry and gold modes into a concentrate and a
tailing. Comminution transforms the size distribution and improves liberation. Classification
splits the stream by size. When the circuit contains a loop, the engine iterates until the
circulating load stabilises. Grade–recovery and kinetic curves are available per stage.

## A two-pronged design

The tool separates **data** from **logic** throughout:

- Minerals, ore profiles and mineral properties are *data* (stoichiometry, densities, magnetic
  and floatability behaviour), not hard-coded logic.
- A registry of separation specs defines every machine's tunable parameters and their bounds,
  automatically driving the UI and validating inputs.
- Display labels are decoupled from technical keys, so the interface reads cleanly in two
  languages while the engine always works on stable keys.

## Installation & usage

Requires Python 3.11+ and the packages in `requirements.txt` (Streamlit, NumPy, pandas,
matplotlib).

```bash
# create/activate an environment, then:
pip install -r requirements.txt
streamlit run app.py
```

Compose an ore and a treatment in the sidebar and main panel, then run the simulation. For a
closed circuit, add a stage-to-stage "recycle" in the multi-route mode.

## Architecture

- `data_models.py` : the central `Stream` object (solids, modal mineralogy, liberation, P80,
  PSD, pulp) and `LiberationState`.
- `mineralogy.py`, `mineral_properties.py` : mineral data (stoichiometry, ore profiles,
  physical properties).
- `separation.py` : the `SEPARATION_SPECS` registry and the shared `separate` operation.
- `laws_gravity.py`, `laws_magnetic.py`, `laws_flotation.py` : the physical response laws.
- `size_classes.py` : size grid and PSD (Rosin–Rammler generation, P80 derivation).
- `comminution.py` : ball mill (Bond's law).
- `classification.py` : hydrocyclone (cut point, Tromp partition).
- `circuit.py` : series circuit engine.
- `flowsheet.py` : graph-based flowsheet engine (topological solve, tear-stream fixed-point
  iteration for circulating load).
- `i18n.py` : translations and display-label helpers.
- `app.py` : the Streamlit interface.
- `tests/` : pytest suite (mass conservation and physical invariants).

## Modelling posture (honest limits)

This is a **phenomenological** model: the response laws capture the correct *direction* of
each effect and realistic *orders of magnitude*, but they are **not calibrated against
specific plant trials**. Several constants (cyclone cut-point constant, native-gold
floatability, gold-carrier densities, default work index, convergence threshold) are
documented placeholders to be tuned against real data. The value is in the coupled,
end-to-end structure where every parameter propagates coherently through the flowsheet —
not in plant-accurate predictions.

## Future work

- **Liberation by mineral association** : SEM associations are already collected; the next
  major modelling effort will let them drive gravity, flotation and magnetic behaviour of
  mixed particles (replacing the scalar-liberation approximation).
- Calibration of the placeholder constants against measured data.
- Richer hydrocyclone physics (density effect, apex/vortex finder).
- Optional full connection editor for arbitrary flowsheet topologies (the engine is already
  generic; only the UI would be extended).

## Author

Fabrice TSAMO - Mining / Geometallurgy Engineer.
GitHub: [fabrice-py](https://github.com/fabrice-py)
LinkedIn account : www.linkedin.com/in/fabrice-tsamo
![tests](https://github.com/fabrice-py/geomet-recovery-predictor/actions/workflows/tests.yml/badge.svg)
