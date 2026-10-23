"""Local experiment persistence and portable CSV export."""
import csv
import io
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS experiments '
               '(id INTEGER PRIMARY KEY, created_utc TEXT NOT NULL, '
               'strategy TEXT NOT NULL, config_json TEXT NOT NULL, '
               'summary_json TEXT NOT NULL, records_json TEXT NOT NULL)')
    return db


def save_experiment(path, cfg, strategy, records, summary):
    with closing(connect(path)) as db, db:
        cur = db.execute('INSERT INTO experiments '
                         '(created_utc,strategy,config_json,summary_json,records_json) '
                         'VALUES (?,?,?,?,?)',
                         (datetime.now(timezone.utc).isoformat(), strategy,
                          json.dumps(asdict(cfg)), json.dumps(summary), json.dumps(records)))
        return cur.lastrowid


def list_experiments(path):
    with closing(connect(path)) as db:
        return db.execute('SELECT id, created_utc, strategy, config_json, summary_json '
                          'FROM experiments ORDER BY id DESC LIMIT 50').fetchall()


def records_csv(records):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)
    return buffer.getvalue()
