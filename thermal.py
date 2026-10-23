"""Deterministic, educational ten-cell thermal model; no hardware control."""
from dataclasses import dataclass
from math import isfinite

STRATEGIES = ('No cooling', 'Fixed flow', 'Thermostatic', 'Adaptive proportional')


@dataclass(frozen=True)
class Config:
    duration_s: int = 1200
    current_a: float = 16.0  # current THROUGH EACH CELL, not pack current
    ambient_c: float = 30.0
    inlet_c: float = 25.0
    initial_c: float = 30.0
    max_flow_lpm: float = 1.0
    profile: str = 'Constant'
    blockage: float = 0.0
    fault_at_s: int = 600
    warning_c: float = 45.0
    uniformity_c: float = 5.0

    def __post_init__(self):
        ranges = {'duration_s': (60, 3600), 'current_a': (0, 25),
                  'ambient_c': (10, 45), 'inlet_c': (10, 40),
                  'initial_c': (10, 50), 'max_flow_lpm': (0.1, 2),
                  'blockage': (0, 0.95), 'fault_at_s': (0, 3600),
                  'warning_c': (35, 60), 'uniformity_c': (1, 10)}
        for key, (low, high) in ranges.items():
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or not isfinite(value) or not low <= value <= high:
                raise ValueError(f'{key} must be finite and between {low} and {high}')
        if not isinstance(self.duration_s, int) or not isinstance(self.fault_at_s, int):
            raise ValueError('Duration and fault time must be whole seconds')
        if self.profile not in ('Constant', 'Urban pulses', 'Charge taper'):
            raise ValueError('Unknown current profile')


def current_at(t, cfg):
    if cfg.profile == 'Urban pulses':
        return cfg.current_a * (0.35 if int(t // 90) % 2 else 1.0)
    if cfg.profile == 'Charge taper':
        return cfg.current_a * max(0.25, 1 - 0.75 * t / cfg.duration_s)
    return cfg.current_a


def neighbours(i):
    row, col = divmod(i, 5)
    return [r * 5 + c for r, c in ((row, col - 1), (row, col + 1), (1 - row, col))
            if 0 <= r < 2 and 0 <= c < 5]


def command_flow(strategy, hottest, on, cfg):
    if strategy == 'No cooling':
        return 0.0, False
    if strategy == 'Fixed flow':
        return cfg.max_flow_lpm, True
    if strategy == 'Thermostatic':
        on = True if hottest >= 38 else False if hottest <= 35 else on
        return cfg.max_flow_lpm if on else 0.0, on
    if strategy == 'Adaptive proportional':
        fraction = min(1.0, max(0.0, (hottest - 33) / 7))
        return cfg.max_flow_lpm * fraction, fraction > 0
    raise ValueError('Unknown cooling strategy')


def make_record(t, temps, flow, actual, power, energy, cfg):
    maximum, minimum = max(temps), min(temps)
    return {'time_s': t, 'current_a': current_at(t, cfg),
            **{f'cell_{i+1}_c': v for i, v in enumerate(temps)},
            'max_c': maximum, 'min_c': minimum, 'spread_c': maximum - minimum,
            'command_lpm': flow, 'actual_lpm': actual, 'pump_w': power,
            'pump_wh': energy,
            'status': 'TEMP ALERT' if maximum >= cfg.warning_c else
                      'SPREAD ALERT' if maximum - minimum >= cfg.uniformity_c else 'NORMAL'}


def simulate(cfg=Config(), strategy='Adaptive proportional'):
    """Explicit Euler at 1 s. Each cell: C*dT/dt = I²R - losses + coupling.

    C=70 J/K, R=0.018..0.02205 ohm; passive conductance=0.05 W/K;
    neighbour conductance=0.08 W/K; coolant G=0.9*flow**0.7 W/K.
    Serial coolant warming uses water cp=4180 J/kg/K and rho=1 kg/L.
    Pump electrical demand proxy=2*command_flow**3 W. Inlet is an imposed
    boundary; refrigeration/reservoir energy is deliberately not modelled.
    """
    if strategy not in STRATEGIES:
        raise ValueError('Unknown cooling strategy')
    temps = [cfg.initial_c] * 10
    on, energy = False, 0.0
    records = [make_record(0, temps, 0, 0, 0, 0, cfg)]
    for t in range(cfg.duration_s):
        flow, on = command_flow(strategy, max(temps), on, cfg)
        actual = flow * (1 - cfg.blockage if t >= cfg.fault_at_s else 1)
        power = 2 * flow ** 3
        energy += power / 3600
        coolant = cfg.inlet_c
        next_temps = []
        for i, temp in enumerate(temps):
            heat = current_at(t, cfg) ** 2 * (0.018 * (1 + 0.025 * i))
            passive = 0.05 * (temp - cfg.ambient_c)
            coupling = 0.08 * sum(temps[j] - temp for j in neighbours(i))
            # At near-zero flow, coolant must not overshoot a cell's temperature.
            capacity_rate = actual / 60 * 4180
            conductance = min(0.9 * actual ** 0.7, capacity_rate) if actual else 0.0
            removed = conductance * (temp - coolant)
            if actual:
                coolant += removed / capacity_rate
            next_temps.append(temp + (heat - passive - removed + coupling) / 70)
        temps = next_temps
        records.append(make_record(t + 1, temps, flow, actual, power, energy, cfg))
    return records


def summarize(records, cfg):
    # Each row t>0 represents the end of a one-second integration interval.
    samples = records[1:]
    return {'peak_c': max(r['max_c'] for r in records),
            'final_c': records[-1]['max_c'],
            'peak_spread_c': max(r['spread_c'] for r in records),
            'seconds_above_limit': sum(r['max_c'] >= cfg.warning_c for r in samples),
            'pump_wh': records[-1]['pump_wh'],
            'delivered_l': sum(r['actual_lpm'] / 60 for r in samples)}


def compare(cfg):
    return {name: {'records': (rows := simulate(cfg, name)),
                   'summary': summarize(rows, cfg)} for name in STRATEGIES}
