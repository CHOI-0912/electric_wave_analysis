import numpy as np
import pandas as pd
import csv
import os
import glob
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCEL_DIR = PROJECT_ROOT / 'data' / 'excel'
OUTPUT_DIR = PROJECT_ROOT / 'output'

# --------------------------------------------------------------------
# Index mapping (plot_wave.py 와의 정합성)
#   - state CSV 의 index 컬럼은 원 데이터(excel) 의 index 와 1:1 대응.
#     plot_wave.py 가 SMOOTH_WINDOW=200 을 centered + edge-padding 으로
#     적용했기 때문에 smoothed[i] 가 raw[i] 와 같은 i 위치를 의미한다.
#   - 따라서 state CSV 에서 "holding [s0-s1]" 라고 적힌 구간은
#     원 데이터 amplitude[s0 : s1+1] 와 그대로 매칭된다.
#
# Why trim?
#   - state[i]="holding" 결정은 smoothed[i±SLOPE_SPAN] 차분에 의존하고,
#     각 smoothed 값은 raw ±SMOOTH_WINDOW/2(=100) 의 평균이다.
#   - 따라서 state[i] 분류가 실제로 의존하는 raw 영역은
#       [i - (SLOPE_SPAN + SMOOTH_WINDOW/2), i + (SLOPE_SPAN + SMOOTH_WINDOW/2 - 1)]
#       = [i-230, i+229]
#   - raw[i] 가 정상상태에 "완전히" 속한다고 보장하려면, 이 230 샘플 footprint
#     전체가 holding segment 안에 들어가야 한다. 즉 양 끝에서
#         TRIM_MARGIN = SMOOTH_WINDOW/2 + SLOPE_SPAN = 100 + 130 = 230
#     샘플을 잘라낸 raw 만 std 계산에 사용한다. 그 결과 사용된 모든 raw 샘플은,
#     "그 샘플의 분류에 영향을 준 모든 이웃 raw" 까지 포함해서 holding 안에 있는
#     fully-safe steady-state 표본이 된다.
# --------------------------------------------------------------------
TRIM_MARGIN = 230        # = SMOOTH_WINDOW//2 + SLOPE_SPAN  (fully-safe)
MIN_TRIMMED_LEN = 50     # 표본표준편차의 통계적 안정성 확보 최소 길이

OUTPUT_DIR.mkdir(exist_ok=True)

summary_rows = []

for xlsx_path in sorted(glob.glob(str(EXCEL_DIR / '*.xlsx'))):
    name = os.path.splitext(os.path.basename(xlsx_path))[0]
    state_csv = OUTPUT_DIR / f'electric_wave_analysis [{name}].csv'
    if not os.path.exists(state_csv):
        print(f'skip {name}: state csv not found')
        continue

    lines = []
    def log(*args):
        m = ' '.join(str(a) for a in args)
        lines.append(m)
        print(*args)

    amplitude = pd.read_excel(xlsx_path, header=None).values[:, 1].astype(float)
    N = len(amplitude)

    states = pd.read_csv(state_csv)['state'].values
    boundaries = np.where(states[1:] != states[:-1])[0] + 1
    segments = np.split(np.arange(N), boundaries)

    log(f'=== {name} ===')
    log(f'N = {N}')
    log(f'TRIM_MARGIN = {TRIM_MARGIN}  (= plot_wave.py SMOOTH_WINDOW // 2)')
    log(f'MIN_TRIMMED_LEN = {MIN_TRIMMED_LEN}')
    log('original index <-> state index 는 1:1 매칭 (centered smoothing + edge padding)')
    log('각 hold segment 양 끝 TRIM_MARGIN 샘플 trim 후 원 데이터로 std(ddof=1) 계산')
    log('')
    log(f'{"kind":5s} {"raw[start-end]":17s} {"trim[start-end]":17s} {"N":>5s} {"mean":>11s} {"std":>13s}')

    seg_rows = []
    high_ss, high_dof = 0.0, 0
    low_ss,  low_dof  = 0.0, 0

    for i, seg in enumerate(segments):
        if states[seg[0]] != 'holding':
            continue
        prev = states[segments[i-1][0]] if i > 0 else None
        nxt  = states[segments[i+1][0]] if i+1 < len(segments) else None
        k = prev if prev in ('rising', 'falling') else nxt
        label = 'high' if k == 'rising' else ('low' if k == 'falling' else 'unk')

        s0, s1 = int(seg[0]), int(seg[-1])
        t0, t1 = s0 + TRIM_MARGIN, s1 - TRIM_MARGIN
        if t1 - t0 + 1 < MIN_TRIMMED_LEN:
            log(f'{label:5s} [{s0:5d}-{s1:5d}]  (trim 후 길이 < {MIN_TRIMMED_LEN}, skip)')
            continue
        x = amplitude[t0:t1+1]
        n  = len(x)
        mu = float(x.mean())
        sd = float(x.std(ddof=1))
        log(f'{label:5s} [{s0:5d}-{s1:5d}] [{t0:5d}-{t1:5d}] {n:5d} {mu:11.6f} {sd:13.8f}')
        seg_rows.append([name, label, s0, s1, t0, t1, n, mu, sd])
        if label == 'high':
            high_ss  += sd * sd * (n - 1)
            high_dof += (n - 1)
        elif label == 'low':
            low_ss  += sd * sd * (n - 1)
            low_dof += (n - 1)

    log('')
    log('-- pooled std  (sigma_p^2 = Sum((n_i-1) * sigma_i^2) / Sum(n_i-1)) --')
    sp_high = float(np.sqrt(high_ss / high_dof)) if high_dof > 0 else float('nan')
    sp_low  = float(np.sqrt(low_ss  / low_dof))  if low_dof  > 0 else float('nan')
    log(f'  high holds (after rising)  : pooled_std = {sp_high:.8f}   (total dof = {high_dof})')
    log(f'  low  holds (after falling) : pooled_std = {sp_low:.8f}    (total dof = {low_dof})')

    summary_rows.append([name, sp_high, sp_low, high_dof, low_dof])

    base = OUTPUT_DIR / f'hold std [{name}]'
    with open(f'{base}.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    with open(f'{base}.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name', 'kind', 'raw_start', 'raw_end',
                    'trim_start', 'trim_end', 'N', 'mean', 'std'])
        w.writerows(seg_rows)

with open(OUTPUT_DIR / 'hold std summary.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['name', 'pooled_std_high', 'pooled_std_low', 'dof_high', 'dof_low'])
    w.writerows(summary_rows)

print()
print(f'wrote {len(summary_rows)} files into {OUTPUT_DIR}')
