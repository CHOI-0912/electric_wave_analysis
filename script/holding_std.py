import numpy as np
import pandas as pd
import csv
import os
import glob
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCEL_DIR = PROJECT_ROOT / 'data' / 'excel'
OUTPUT_DIR = PROJECT_ROOT / 'output'

# Trim is ratio-based by default (adapts to segment length), but capped at a
# fixed maximum per side. Both ratio and max-trim are auto-derived from
# Nothing data via separate sweeps (elbow = 95% of std drop).
KEEP_MIN_LENGTH = 0
RATIO_CANDIDATES = np.arange(0.0, 0.46, 0.01)
TRIM_CANDIDATES = np.arange(0, 351, 5)  # samples per side
ELBOW_FRACTION = 0.95


def get_holding_segments(name):
    xlsx_path = EXCEL_DIR / f'{name}.xlsx'
    state_csv = OUTPUT_DIR / f'electric_wave_analysis [{name}].csv'
    if not os.path.exists(xlsx_path) or not os.path.exists(state_csv):
        return None, []
    amplitude = pd.read_excel(xlsx_path, header=None).values[:, 1].astype(float)
    state = pd.read_csv(state_csv)['state'].values
    if len(state) != len(amplitude):
        return amplitude, []
    is_holding = (state == 'holding')
    transitions = np.diff(is_holding.astype(int))
    starts = np.where(transitions == 1)[0] + 1
    ends = np.where(transitions == -1)[0]
    if is_holding[0]:
        starts = np.concatenate([[0], starts])
    if is_holding[-1]:
        ends = np.concatenate([ends, [len(state) - 1]])
    return amplitude, list(zip(starts.tolist(), ends.tolist()))


def avg_std_at_ratio(segments_data, ratio):
    stds = []
    for amp, s, e in segments_data:
        L = e - s + 1
        trim = int(round(L * ratio))
        a = s + trim
        b = e - trim
        L_t = b - a + 1
        if L_t < 30:
            continue
        stds.append(amp[a:b + 1].std(ddof=1))
    return float(np.mean(stds)) if stds else np.nan


def avg_std_at_fixed(segments_data, fixed_trim):
    stds = []
    for amp, s, e in segments_data:
        a = s + fixed_trim
        b = e - fixed_trim
        L_t = b - a + 1
        if L_t < 30:
            continue
        stds.append(amp[a:b + 1].std(ddof=1))
    return float(np.mean(stds)) if stds else np.nan


def find_elbow(candidates, stds):
    if all(np.isnan(s) for s in stds):
        return None
    std_max = stds[0]
    std_min = float(np.nanmin(stds))
    threshold = std_min + (1 - ELBOW_FRACTION) * (std_max - std_min)
    for c, s in zip(candidates, stds):
        if not np.isnan(s) and s <= threshold:
            return c
    return candidates[-1]


def find_optimal_from_nothing():
    nothing_segments = []
    for name in ['Nothing(1)', 'Nothing(2)']:
        amp, segs = get_holding_segments(name)
        if amp is None:
            continue
        for s, e in segs:
            if e - s + 1 >= 200:
                nothing_segments.append((amp, s, e))

    if not nothing_segments:
        print('[!] Nothing data unavailable, falling back to RATIO=0.2, MAX_TRIM=100')
        return 0.2, 100

    ratio_stds = [avg_std_at_ratio(nothing_segments, float(r)) for r in RATIO_CANDIDATES]
    trim_stds = [avg_std_at_fixed(nothing_segments, int(t)) for t in TRIM_CANDIDATES]

    ratio_path = OUTPUT_DIR / 'nothing_ratio_sweep.csv'
    with open(ratio_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ratio', 'mean_std'])
        for r, s in zip(RATIO_CANDIDATES, ratio_stds):
            writer.writerow([f'{float(r):.2f}', f'{s:.6e}'])

    trim_path = OUTPUT_DIR / 'nothing_trim_sweep.csv'
    with open(trim_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['trim', 'mean_std'])
        for t, s in zip(TRIM_CANDIDATES, trim_stds):
            writer.writerow([int(t), f'{s:.6e}'])

    print('[Nothing ratio sweep]')
    print('  ratio   mean_std')
    for r, s in zip(RATIO_CANDIDATES, ratio_stds):
        print(f'  {r:5.2f}  {s:.6e}')
    print(f'  (saved to {ratio_path})')

    print('\n[Nothing fixed-trim sweep]')
    print('  trim  mean_std')
    for t, s in zip(TRIM_CANDIDATES, trim_stds):
        print(f'  {int(t):4d}  {s:.6e}')
    print(f'  (saved to {trim_path})')

    optimal_ratio = float(find_elbow(RATIO_CANDIDATES, ratio_stds))
    optimal_trim = int(find_elbow(TRIM_CANDIDATES, trim_stds))

    print(f'\n→ TRIM_RATIO = {optimal_ratio:.2f} (default), MAX_TRIM = {optimal_trim} (cap)')
    return optimal_ratio, optimal_trim


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    TRIM_RATIO, MAX_TRIM = find_optimal_from_nothing()

    rows = []
    for xlsx_path in sorted(glob.glob(str(EXCEL_DIR / '*.xlsx'))):
        name = os.path.splitext(os.path.basename(xlsx_path))[0]
        amp, segs = get_holding_segments(name)
        if amp is None:
            print(f'[{name}] skipped - missing input')
            continue

        # Per-file dynamic range: p95 - p5 of the original amplitude.
        # std / dyn_range gives the noise level as a fraction of signal swing.
        p95 = float(np.percentile(amp, 95))
        p5 = float(np.percentile(amp, 5))
        dyn_range = p95 - p5

        print(f'\n[{name}] dyn_range (p95-p5) = {dyn_range:.6f}')
        print(f'  seg                 trim                  mean         std    std/range  kept')
        for s, e in segs:
            L = e - s + 1
            trim_ratio_based = int(round(L * TRIM_RATIO))
            trim = min(trim_ratio_based, MAX_TRIM)  # cap by fixed max
            a = s + trim
            b = e - trim
            L_t = b - a + 1
            kept = L_t >= KEEP_MIN_LENGTH

            if L_t > 0:
                seg = amp[a:b + 1]
                mean = float(seg.mean())
                std = float(seg.std(ddof=1)) if L_t > 1 else 0.0
            else:
                mean = float('nan')
                std = float('nan')

            std_pct = (std / dyn_range * 100) if dyn_range > 0 and not np.isnan(std) else float('nan')

            marker = 'T' if kept else 'F'
            print(f'  [{s:5d}-{e:5d}] {L:5d}  [{a:5d}-{b:5d}] {L_t:5d}  {mean:11.6f}  {std:11.6e}  {std_pct:6.2f}%  {marker}')
            rows.append({
                'file': name,
                'seg_start': int(s),
                'seg_end': int(e),
                'seg_length': int(L),
                'trim_ratio': round(TRIM_RATIO, 2),
                'max_trim': int(MAX_TRIM),
                'trim_applied': int(trim),
                'trim_start': int(a),
                'trim_end': int(b),
                'trim_length': int(L_t),
                'mean': mean,
                'std': std,
                'dyn_range': dyn_range,
                'std_pct_of_range': std_pct,
                'kept': kept,
            })

    out_path = OUTPUT_DIR / 'holding_std.csv'
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    kept_count = sum(1 for r in rows if r['kept'])
    print(f'\nSaved {out_path} ({len(rows)} segments, {kept_count} kept)')
    print(f'  TRIM_RATIO={TRIM_RATIO:.2f} (default), MAX_TRIM={MAX_TRIM} (cap)')


if __name__ == '__main__':
    main()
