"""ThermoGuard: a Python-authored Streamlit frontend and Python backend."""
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from storage import list_experiments, records_csv, save_experiment
from thermal import Config, STRATEGIES, compare

st.set_page_config(page_title='ThermoGuard | Battery Thermal Lab', page_icon='🔋', layout='wide')
st.title('ThermoGuard')
st.caption('EV BATTERY THERMAL LAB  /  MONITOR · SIMULATE · COMPARE')
st.info('Software simulation • 10 virtual cells • Rule-based cooling • No physical sensors connected')

with st.sidebar:
    st.header('Experiment setup')
    with st.form('setup'):
        st.caption('Apply settings to generate a new experiment.')
        duration = st.slider('Duration (seconds)', 60, 3600, 1200, 60)
        current = st.slider('Current per cell (A)', 0.0, 25.0, 16.0, 0.5)
        profile = st.selectbox('Current profile', ['Constant', 'Urban pulses', 'Charge taper'])
        ambient = st.slider('Ambient temperature (°C)', 10.0, 45.0, 30.0)
        inlet = st.slider('Coolant inlet (°C)', 10.0, 40.0, 25.0)
        initial = st.slider('Initial cell temperature (°C)', 10.0, 50.0, 30.0)
        flow = st.slider('Maximum commanded flow (L/min)', 0.1, 2.0, 1.0, 0.1)
        st.subheader('Fault injection')
        blockage = st.slider('Flow reduction after fault (%)', 0, 95, 0, 5)
        fault = st.slider('Fault starts at (seconds)', 0, 3600, 600, 60)
        st.subheader('Demonstration alert limits')
        warning = st.slider('Temperature alert (°C)', 35.0, 60.0, 45.0)
        uniformity = st.slider('Cell temperature spread alert (°C)', 1.0, 10.0, 5.0)
        applied = st.form_submit_button('Apply and simulate', type='primary', width='stretch')
    st.caption('Alert limits are configurable teaching values, not certified battery limits.')

if 'cfg' not in st.session_state or applied:
    st.session_state.cfg = Config(duration, current, ambient, inlet, initial, flow,
                                  profile, blockage / 100, fault, warning, uniformity)
    st.session_state.cursor = 0
    st.session_state.playing = False

cfg = st.session_state.cfg
if cfg.blockage and cfg.fault_at_s >= cfg.duration_s:
    st.info('The selected flow fault starts after the final simulated interval, so this run has no flow reduction.')


@st.cache_data(show_spinner='Solving the thermal model…')
def experiments(settings):
    return compare(Config(**settings))


results = experiments(asdict(cfg))
dashboard, comparison, history, methodology = st.tabs(['Battery monitor', 'Cooling comparison', 'Saved experiments', 'Model and assumptions'])

with dashboard:
    strategy = st.selectbox('Cooling strategy', STRATEGIES, index=3)
    records = results[strategy]['records']
    rows = pd.DataFrame(records)
    st.caption('Replay the calculated experiment. One simulation second is one model step; playback is accelerated.')
    a, b, c = st.columns([1, 1, 3])
    if a.button('▶ Play / pause', width='stretch'):
        st.session_state.playing = not st.session_state.playing
    if b.button('↺ Reset', width='stretch'):
        st.session_state.cursor = 0
        st.session_state.playing = False
    speed = c.select_slider('Simulation seconds per refresh', [1, 5, 10, 30, 60], value=10)

    @st.fragment(run_every=0.5)
    def monitor():
        if st.session_state.playing:
            st.session_state.cursor = min(cfg.duration_s, st.session_state.cursor + speed)
            if st.session_state.cursor >= cfg.duration_s:
                st.session_state.playing = False
        cursor = st.slider('Replay time (seconds)', 0, cfg.duration_s, key='cursor')
        r = records[cursor]
        cells = st.columns(4)
        cells[0].metric('Hottest cell', f"{r['max_c']:.1f} °C")
        cells[1].metric('Cell spread', f"{r['spread_c']:.2f} °C")
        cells[2].metric('Delivered coolant flow', f"{r['actual_lpm']:.2f} L/min")
        cells[3].metric('Pump energy so far', f"{r['pump_wh']:.3f} Wh")
        if r['status'] == 'TEMP ALERT':
            st.error(f"Temperature alert: at least one virtual cell is at or above {cfg.warning_c:g} °C.")
        elif r['status'] == 'SPREAD ALERT':
            st.warning(f"Uniformity alert: cell temperature spread is at or above {cfg.uniformity_c:g} °C.")
        else:
            st.success('Within the selected demonstration alert limits.')
        if r['max_c'] >= cfg.warning_c and r['spread_c'] >= cfg.uniformity_c:
            st.warning('Cell temperature spread also exceeds the selected limit.')
        st.subheader('Virtual battery pack')
        pack = pd.DataFrame([{'column': i % 5 + 1, 'row': i // 5 + 1,
                              'temperature': r[f'cell_{i+1}_c'],
                              'label': f"C{i+1:02d} · {r[f'cell_{i+1}_c']:.1f} °C"} for i in range(10)])
        base = alt.Chart(pack).encode(x=alt.X('column:O', axis=None), y=alt.Y('row:O', axis=None))
        heatmap = base.mark_rect(cornerRadius=12, stroke='#FFFFFF', strokeWidth=5).encode(
            color=alt.Color('temperature:Q', title='°C', scale=alt.Scale(
                domain=[10, cfg.warning_c, max(60, r['max_c'])], range=['#276985', '#E9AB4B', '#BD3D4F'])),
            tooltip=['label'])
        labels = base.mark_text(fontSize=17, color='white', fontWeight='bold').encode(text='label:N')
        st.altair_chart((heatmap + labels).properties(height=205), width='stretch')
        st.caption('2 × 5 layout • Coolant visits cells C01 through C10 in sequence • Each cell exchanges heat with its grid neighbours')
        visible = rows.iloc[:cursor+1]
        sampled = visible.iloc[::max(1, len(visible) // 2000 + 1)]
        plot = sampled[['time_s', 'max_c', 'min_c']].rename(columns={
            'max_c':'Hottest cell', 'min_c':'Coolest cell'}).melt('time_s', var_name='Series', value_name='Temperature (°C)')
        chart = alt.Chart(plot).mark_line(strokeWidth=2.5).encode(
            x=alt.X('time_s:Q', title='Simulation time (s)', scale=alt.Scale(domain=[0, cfg.duration_s])),
            y=alt.Y('Temperature (°C):Q', scale=alt.Scale(zero=False)),
            color=alt.Color('Series:N', scale=alt.Scale(domain=['Hottest cell', 'Coolest cell'], range=['#E9AB4B', '#55B8C0'])),
            tooltip=['time_s', 'Temperature (°C)', 'Series'])
        limit = alt.Chart(pd.DataFrame({'limit':[cfg.warning_c]})).mark_rule(color='#EF6072', strokeDash=[6,4]).encode(y='limit:Q')
        st.altair_chart((chart + limit).properties(height=260), width='stretch')
        with st.expander('Cell readings and pump command'):
            st.dataframe(pd.DataFrame({'Cell':[f'C{i+1:02d}' for i in range(10)],
                                       'Temperature (°C)':[r[f'cell_{i+1}_c'] for i in range(10)]}), hide_index=True)
            st.write(f"Current per cell: {r['current_a']:.1f} A · Commanded flow: {r['command_lpm']:.2f} L/min · Pump demand: {r['pump_w']:.2f} W")
    monitor()
    st.download_button('Download this experiment CSV', records_csv(records), f'thermoguard_{strategy.replace(" ", "_")}.csv', 'text/csv')
    if st.button('Save this experiment locally'):
        try:
            identifier = save_experiment(Path(__file__).parent / 'data' / 'experiments.db', cfg, strategy, records, results[strategy]['summary'])
            st.success(f'Saved experiment #{identifier}.')
        except (OSError, sqlite3.Error) as exc:
            st.error(f'Unable to save the experiment: {exc}')

with comparison:
    st.subheader('Same battery conditions. Four cooling strategies.')
    st.caption('All strategies use identical initial conditions, current profile and fault settings.')
    summaries = pd.DataFrame([{'Strategy': name, **v['summary']} for name, v in results.items()])
    st.dataframe(summaries.rename(columns={'peak_c':'Peak (°C)', 'final_c':'Final maximum (°C)',
        'peak_spread_c':'Peak spread (°C)', 'seconds_above_limit':'Seconds at or above limit',
        'pump_wh':'Pump energy (Wh)', 'delivered_l':'Circulated volume (L)'}).round(3), hide_index=True, width='stretch')
    full = pd.concat([pd.DataFrame(v['records']).assign(Strategy=name) for name, v in results.items()])
    st.altair_chart(alt.Chart(full.iloc[::5]).mark_line(strokeWidth=2.3).encode(
        x=alt.X('time_s:Q', title='Time (s)'), y=alt.Y('max_c:Q', title='Maximum cell temperature (°C)', scale=alt.Scale(zero=False)),
        color='Strategy:N', tooltip=['Strategy', 'time_s', 'max_c']).properties(height=350), width='stretch')
    st.bar_chart(summaries.set_index('Strategy')[['pump_wh']], y_label='Pump energy (Wh)')
    st.download_button('Download comparison CSV', summaries.to_csv(index=False), 'cooling_comparison.csv', 'text/csv')
    st.caption('Pump energy excludes any chiller or reservoir conditioning. Circulated volume is cumulative throughput, not coolant consumed.')

with history:
    st.subheader('Local experiment log')
    if st.button('Refresh saved experiments'):
        st.rerun()
    try:
        saved = list_experiments(Path(__file__).parent / 'data' / 'experiments.db')
        if not saved:
            st.info('Save an experiment from the battery monitor to add it here.')
        for identifier, created, name, settings, summary in saved:
            with st.expander(f'#{identifier} · {name} · {created}'):
                st.json({'settings':json.loads(settings), 'results':json.loads(summary)})
    except (OSError, sqlite3.Error) as exc:
        st.error(f'Unable to read the experiment log: {exc}')

with methodology:
    st.subheader('An explainable thermal model')
    st.write('Each cell stores heat, generates resistive heat, exchanges heat with neighbouring cells and loses heat to ambient air and flowing coolant. A one-second Euler step updates all cells from their previous temperatures.')
    st.latex(r'C\frac{dT_i}{dt}=I^2R_i-G_a(T_i-T_a)-G_f(T_i-T_{f,i})+G_n\sum_{j\in N_i}(T_j-T_i)')
    st.write('Parameters: C = 70 J/K per cell; R = 0.018–0.02205 Ω; ambient conductance = 0.05 W/K; neighbour conductance = 0.08 W/K; coolant conductance = 0.9 × actual flow^0.7 W/K, with flow numerically expressed in L/min.')
    st.caption('At near-zero flow, effective coolant conductance is capped at its heat-capacity rate to prevent coolant-temperature overshoot.')
    st.write('Fixed flow runs continuously. Thermostatic cooling switches on at 38 °C and off at 35 °C. Adaptive proportional cooling increases flow linearly from zero at 33 °C to maximum at 40 °C. These thresholds are fixed controller settings; alert limits are separate.')
    st.write('A fault reduces delivered flow while the commanded pump demand remains unchanged. The model does not calculate channel pressure drop, electrochemical reactions, state of charge, battery ageing, thermal runaway, or nanofluid properties. The constant-current profile is an imposed thermal stress, not a capacity-aware charging model.')
    st.write('The coolant inlet temperature is imposed. A colder inlet may require external refrigeration, whose energy is excluded. Parameters are illustrative and uncalibrated; results support software experiments, not battery design or physical safety validation. This version contains no machine learning.')
    st.json(asdict(cfg))
    st.download_button('Download experiment settings', json.dumps(asdict(cfg), indent=2),
                       'experiment_settings.json', 'application/json')
