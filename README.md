# ThermoGuard

A Python application combining a ten-cell EV battery temperature dashboard with a cooling-strategy simulator. The interface is authored in Python using Streamlit; the simulation, controller and experiment storage are also Python. No HTML, CSS or JavaScript source is required.

## Run the dashboard

Install Python 3.10 or later. Open a terminal in this folder:

```sh
python -m venv .venv
```

Activate the environment on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```sh
source .venv/bin/activate
```

Then install and start:

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Alternatively, run `python launch.py`; it starts the app from any working directory and checks whether the packages are installed.

Open the local address printed by Streamlit. Initial package installation needs internet; after installation the model runs locally without external APIs or accounts. LaTeX display may depend on browser font assets.

## Demonstrate the project

1. Open Battery monitor and choose a cooling strategy.
2. Press Play or move the replay slider to inspect all ten virtual cells.
3. Open Cooling comparison to compare the same operating conditions across no cooling, fixed flow, thermostatic and proportional control.
4. In Experiment setup select an 80% flow reduction starting at 600 seconds. Press Apply and simulate, then inspect the effect of the fault.
5. Download CSV results or save an experiment to the local SQLite log.

The animation replays an already calculated experiment; it is not a physical sensor feed. Changing sidebar fields takes effect only when Apply and simulate is pressed. All four controllers are recalculated under the same conditions. The current setting refers to current through each cell.

## Reproduce the report and run tests

The backend uses only the Python standard library. These commands work without Streamlit:

```sh
python -m unittest discover -s tests -v
python run_experiments.py --output sample_results
```

The benchmark uses 1,200 seconds, 16 A per cell, 30 °C ambient and initial temperature, 25 °C coolant inlet and a maximum flow of 1 L/min. Additional experiments cover an 80% flow reduction at 600 s and a pulsed current profile. Sample results are included.

## Code structure

- `app.py`: Streamlit interface, replay, cell map, charts, downloads and experiment log.
- `thermal.py`: validated configuration, thermal integration, controllers and metrics.
- `storage.py`: SQLite persistence and CSV export.
- `run_experiments.py`: reproducible benchmark generation.
- `launch.py`: dashboard launcher with dependency checks.
- `tests/test_thermal.py`: equilibrium, energy balance, controller, fault and storage verification.
- `tests/test_dashboard.py`: interface integration checks, skipped when Streamlit is unavailable.
- `.streamlit/config.toml`: application theme.

Runtime experiment data are stored in `data/experiments.db`, created when the app runs. SQLite is an embedded database accessed by Python. Avoid committing personal experiment logs.

## Model and scope

The model solves a lumped heat balance for a 2 × 5 cell arrangement at one-second steps. Each cell generates I²R heat, exchanges heat with neighbouring cells, and transfers heat to ambient air and a serial coolant path. A water-like coolant warms along the path. Cell resistance varies from 0.018 to 0.02205 ohm to create illustrative cell variation.

Parameters are illustrative: cell heat capacity 70 J/K, passive conductance 0.05 W/K, neighbour conductance 0.08 W/K and coolant conductance 0.9 × actual_flow^0.7 W/K, with flow expressed numerically in L/min. Effective conductance is capped at the coolant heat-capacity rate to prevent unphysical coolant-temperature overshoot at near-zero flow. These are not calibrated microchannel correlations. The controller uses the hottest cell: thermostat on at 38 °C and off at 35 °C; proportional flow rises from zero at 33 °C to full flow at 40 °C. Alert limits are separate configurable teaching settings.

Pump demand is the proxy 2 × commanded_flow³ W, with flow in L/min. Faults reduce actual flow but leave pump command and proxy energy unchanged. This illustrates loss of cooling effectiveness; it does not solve pump curves or blockage pressure drop.

The coolant inlet temperature is imposed. Chiller energy, reservoir dynamics, electrochemistry, state of charge, ageing, nanofluid properties, 3D CFD and thermal runaway are outside the model. An imposed sustained current is a thermal stress case, not a capacity-aware charge simulation. Accumulated circulated litres are throughput, not coolant consumption. Use results for teaching and software comparison only; no physical battery is controlled and no hardware validation is claimed.

This project implements monitoring and rule-based cooling simulation. It does not claim machine learning or a sensor-synchronised digital twin. Sensor input and validated microchannel models are possible future extensions.

## Academic report

The accompanying Word report follows the supplied institution template. Fill in student names and roll numbers, course code/name, guide details, date and GitHub repository URL before submission. The certificate requires institutional review and signatures. Benchmark results must remain identified as simulation results.

## References

- Supplied use case KJS-CES-02, AI-Enabled Micro-channel Battery Thermal Management System for Electric Vehicles.
- https://docs.streamlit.io/develop/concepts/architecture/architecture
- https://docs.python.org/3/library/sqlite3.html
- https://docs.python.org/3/library/unittest.html
- https://docs.nlr.gov/docs/fy16osti/66260.pdf
