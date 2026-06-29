#!/usr/bin/env python3
"""Write Engineering Time Study percentages into a team's response tab.

Takes a JSON mapping of seniority band -> the four bucket percentages and
writes each into the correct column (rows 8-11) via the `gws` CLI (reuses
your Google auth). Validates every column totals 100 before writing.

Data JSON shape (whole-number percents):
{
  "Mid level":     {"Development Activity": 30, "Project Meetings": 0,
                    "Non-project meetings": 40, "Admin and other": 30},
  "Senior":        {...},
  "Distinguished": {...},
  "Manager":       {...}
}

Usage:
  python3 fill_survey.py --spreadsheet <ID> --tab "Content Squad" \\
    --data /tmp/survey_values.json [--dry-run]
"""
import argparse, json, subprocess, sys

COL = {'Associate': 'B', 'Mid level': 'C', 'Senior': 'D', 'Staff': 'E',
       'Principal': 'F', 'Distinguished': 'G', 'Manager': 'H'}
ROW = {'Development Activity': 8, 'Project Meetings': 9,
       'Non-project meetings': 10, 'Admin and other': 11}
CATS = list(ROW.keys())


def gws_update(spreadsheet, a1_range, values, dry):
    params = json.dumps({'spreadsheetId': spreadsheet, 'range': a1_range,
                         'valueInputOption': 'USER_ENTERED'})
    body = json.dumps({'values': values})
    cmd = ['gws', 'sheets', 'spreadsheets', 'values', 'update',
           '--params', params, '--json', body]
    if dry:
        print(f"  [dry-run] {a1_range} <- {[r[0] for r in values]}")
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ERROR writing {a1_range}: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    print(f"  wrote {a1_range}: {[r2[0] for r2 in values]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spreadsheet', required=True)
    ap.add_argument('--tab', required=True)
    ap.add_argument('--data', required=True)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    data = json.load(open(args.data))
    # allow a wrapper like {"band_avg": {...}, "manager": {...}}
    if 'band_avg' in data:
        merged = dict(data['band_avg'])
        if data.get('manager'):
            merged['Manager'] = data['manager']
        data = merged

    # validate
    for band, vals in data.items():
        if band not in COL:
            print(f"  unknown band '{band}' (expected one of {list(COL)})", file=sys.stderr)
            sys.exit(1)
        total = sum(vals.get(c, 0) for c in CATS)
        if round(total) != 100:
            print(f"  {band} totals {total}%, must be 100", file=sys.stderr)
            sys.exit(1)

    for band, vals in data.items():
        col = COL[band]
        rng = f"'{args.tab}'!{col}{ROW['Development Activity']}:{col}{ROW['Admin and other']}"
        values = [[f"{int(round(vals[c]))}%"] for c in CATS]   # rows 8-11 in order
        gws_update(args.spreadsheet, rng, values, args.dry_run)
    print("Done." if not args.dry_run else "Dry run complete.")


if __name__ == '__main__':
    main()
