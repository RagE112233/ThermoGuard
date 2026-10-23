"""Reproduce the report's benchmark without installing dashboard packages."""
import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from thermal import Config, compare
from storage import records_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('sample_results'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = {'baseline': Config(),
                 'flow_fault': Config(blockage=.8, fault_at_s=600),
                 'urban_pulses': Config(profile='Urban pulses')}
    combined = []
    for scenario, cfg in scenarios.items():
        folder = args.output/scenario
        folder.mkdir(exist_ok=True)
        (folder/'settings.json').write_text(json.dumps(asdict(cfg), indent=2))
        for name, result in compare(cfg).items():
            (folder/(name.lower().replace(' ', '_')+'.csv')).write_text(records_csv(result['records']))
            combined.append({'scenario':scenario, 'strategy':name, **result['summary']})
    with (args.output/'comparison.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file, fieldnames=combined[0].keys())
        writer.writeheader()
        writer.writerows(combined)
    (args.output/'comparison.json').write_text(json.dumps(combined,indent=2))
    print(json.dumps(combined,indent=2))


if __name__ == '__main__':
    main()
