"""Export the prototype warehouse (SQLite) to BigQuery so BQML / Vertex AI can train on it.

    python scripts/export_bigquery.py --project my-project --dataset phc_pulse

Requires the `bq` CLI (Google Cloud SDK) and an existing dataset created from
bigquery/schema.sql. Tables are loaded with WRITE_TRUNCATE semantics (--replace).
"""
import argparse
import csv
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

QUERIES = {
    "phcs": "SELECT id, code, name, block, district_code, state_code, lat, lon, beds_total,"
            " staff_sanctioned, CASE is_24x7 WHEN 1 THEN 'true' ELSE 'false' END, language,"
            " supply_anchor, nin FROM phcs",
    "stock_daily": "SELECT s.phc_id, p.state_code, s.drug_code, s.day, s.opening, s.received,"
                   " s.dispensed, s.unmet, s.adjustment, s.closing, s.source"
                   " FROM stock_daily s JOIN phcs p ON p.id = s.phc_id",
    "footfall_daily": "SELECT f.phc_id, p.state_code, f.day, f.opd, f.fever, f.diarrhoea,"
                      " f.respiratory, f.beds_occupied, f.staff_present, f.source"
                      " FROM footfall_daily f JOIN phcs p ON p.id = f.phc_id",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--dataset", default="phc_pulse")
    ap.add_argument("--db", default=os.getenv("PHC_DB_PATH", str(ROOT / "backend" / "data" / "phc_pulse.db")))
    args = ap.parse_args()

    if not Path(args.db).exists():
        from app.seed import seed_database  # generate the synthetic warehouse first
        seed_database()

    conn = sqlite3.connect(args.db)
    with tempfile.TemporaryDirectory() as tmp:
        for table, sql in QUERIES.items():
            path = Path(tmp) / f"{table}.csv"
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                for row in conn.execute(sql):
                    w.writerow(["" if v is None else v for v in row])
            print(f"loading {table} ...")
            subprocess.run(["bq", "load", "--replace", "--source_format=CSV", f"--project_id={args.project}",
                            f"{args.dataset}.{table}", str(path)], check=True)
    print("done")


if __name__ == "__main__":
    main()
