# Design Notes — Geometallurgical Flowsheet Simulator

*[Version française détaillée : DESIGN.md](DESIGN.md)*

This document summarises the design decisions and architecture of the simulator. The French
`DESIGN.md` is the detailed design log; this is a synthetic technical overview.

## 1. Vision

A process simulator for mineral processing flowsheets where **every machine parameter has a
real, physically-motivated effect**. The goal is an operational, coherent tool  not a toy
in which mineralogy, liberation, particle size and machine settings all propagate consistently
from feed to products, including through closed circuits with circulating load.

## 2. Data flows in two directions

- **Forward (prediction):** from ore characterization (mineralogy, liberation, PSD) through the
  flowsheet to predicted products (masses, grades, recoveries).
- **Backward (calibration, partial):** measured data (XRF, SEM liberation) can override or be
  compared against model-reconstructed values, so the model can be confronted with reality.

## 3. Layered architecture

The tool strictly separates **data** from **logic**:

- **Data:** minerals (stoichiometry), ore profiles (Dirichlet compositions), mineral properties
  (density, magnetic behaviour, floatability). Adding a mineral or a profile is adding data, not
  code.
- **Registry:** `SEPARATION_SPECS` declares each machine's tunable parameters and their bounds.
  It drives the UI automatically and validates inputs (out-of-bounds raises).
- **Logic:** response laws (gravity, magnetic, flotation), comminution (Bond), classification
  (cyclone), and the flowsheet engine. Logic never hard-codes mineral data.
- **Presentation:** display labels are decoupled from technical keys, enabling a clean bilingual
  (FR/EN) UI while the engine always operates on stable keys.

## 4. The `Stream` object

The central data schema. A `Stream` carries: solids tonnage, modal mineralogy, a
`LiberationState` (liberation degree per mineral), P80, the full PSD curve, pulp state
(% solids, SG), and assays — including multi-mode gold (native / sulfide-hosted / gangue-hosted,
each tracked separately so gold modes travel intact through the circuit).

## 5. Separation engine

**Three things kept separate, never mixed:** the ore (data), the machine settings (registry),
and the response law (logic). A common `separate(stream, recovery_by_mineral, ...)` operation
splits any feed into a concentrate and a tailing, conserving mass and propagating mineralogy,
chemistry, PSD and gold modes.

Implemented routes: gravity (shaking table, spiral, Falcon  via a cut density d50 and a
sharpness Ep), magnetic (LIMS/WHIMS, wet/dry via field and susceptibility weighted by
liberation), flotation (kinetic, via collector/frother/pH/residence). Every parameter and the
feed P80 have an audited, non-decorative effect on recovery.

## 6. Particle size distribution (PSD)

Discrete size classes on a **user-editable grid** common to the whole flowsheet. The PSD is the
truth; the **P80 is derived** from it. Initial PSDs are generated with Rosin–Rammler; a measured
PSD can be entered manually or loaded from CSV. The PSD flows through the entire model and is
transformed by comminution and classification.

## 7. Comminution — ball mill (Bond's law)

A **transformer** unit (one stream in, one finer stream out; mass and mineralogy unchanged,
liberation improved). Bond's law relates specific energy (kWh/t) and ore work index to the size
reduction: the output P80 is computed, the PSD rebuilt, and liberation recomputed. More energy →
finer; harder ore (higher Wi) → less reduction. A mill can only reduce, never coarsen.

## 8. Classification — hydrocyclone

Splits a stream by **size** into overflow (fines) and underflow (coarse). An empirical cut point
d50 is derived from diameter and pressure; each size class is partitioned by a **Tromp partition
curve**. Mineralogy is currently size-neutral (a density effect is planned). The continuing
stream (overflow or underflow) is user-selectable.

## 9. Flowsheet engine & circulating load

The key piece. A circuit is a **graph** of nodes (units) and connections (which output feeds
which node). Acyclic circuits are solved in one pass by **topological sort**. Closed circuits are
solved by the **tear-stream / fixed-point method**: back edges are cut and assumed empty, then
the loop is iterated reinjecting the estimated recycle stream until the flow stabilises.

Convergence is monitored carefully: slow convergence is distinguished from true divergence
(growing increments), a circulating-load ceiling (10× feed) guards against runaway, and explicit
statuses are returned (`converged`, `diverged`, `circulating_load_too_high`, `max_iter_reached`).
**Global mass conservation at steady state is verified by an automated test.**

The engine is **generic** (any topology). The UI exposes a simpler "series + recycles" model;
extending to a full connection editor would only touch the UI, not the engine.

## 10. Real characterization data

Optional, manual entry and CSV import for each:
- **PSD** : measured size distribution (defines grid + proportions).
- **XRD** : measured mineralogy (custom mode; user completes intrinsic properties).
- **XRF** : bulk chemistry, **compared** against the chemistry reconstructed from mineralogy
  (validation of the mineralogy). Unknown elements are accepted for extensibility.
- **SEM** : measured liberation per mineral, **overriding** the P80-derived estimate.
  Associations are collected for a future association-based liberation model.

## 11. Validation

- **Automated tests (pytest):** mass conservation across separation, series circuits, cyclone
  and circulating load; physical invariants (PSD sums to 1, Bond monotonicity, mill never
  coarsens, parameter bounds enforced).
- **Manual + in-app testing** at each step to validate both the physics (isolated unit tests)
  and the wiring (behaviour inside the app).

## 12. Honest limits (modelling posture)

Phenomenological model: correct **direction** of effects and realistic **orders of magnitude**,
but **not calibrated against specific plant trials**. Several constants are documented
placeholders to tune against real data (cyclone cut-point constant, native-gold floatability,
gold-carrier densities, default work index, convergence threshold). The value lies in the
coherent, coupled, end-to-end structure — not in plant-accurate predictions.

## 13. Key design decisions

| Topic | Decision |
|---|---|
| Liberation | Scalar per mineral (Option A), enriched by measured SEM liberation; association-based (Option B) is the next major effort |
| Routes | Gravity (table/spiral/Falcon), magnetic (LIMS/WHIMS), flotation, ball mill (Bond), hydrocyclone (Tromp) |
| PSD | Full Rosin–Rammler PSD, editable grid, P80 derived; flows through grinding and classification |
| Circulating load | General graph solver (tear stream / fixed point), all topologies, robust convergence |
| Real data | PSD, XRD, XRF (compared), SEM (measured liberation) — manual + CSV |
| Data vs logic | Strict separation throughout; UI and validation driven by a parameter registry |

## 14. Future work

- **Association-based liberation (Option B):** SEM associations already collected will drive the
  gravity/flotation/magnetic behaviour of mixed particles.
- Calibration of placeholder constants against measured data.
- Richer hydrocyclone physics (density effect, apex/vortex finder).
- Optional full connection editor for arbitrary topologies.
