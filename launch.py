"""Start ThermoGuard from any working directory."""
import importlib.util
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    missing = [name for name in ('streamlit', 'pandas', 'altair')
               if importlib.util.find_spec(name) is None]
    if missing:
        print('ThermoGuard needs these packages: ' + ', '.join(missing))
        print('Install the project dependencies first:')
        print(f'"{sys.executable}" -m pip install -r "{root / "requirements.txt"}"')
        return 1
    return subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(root / 'app.py')], cwd=root)


if __name__ == '__main__':
    raise SystemExit(main())
