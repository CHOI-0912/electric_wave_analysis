import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import csv
import os
import glob
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXCEL_DIR = PROJECT_ROOT / 'data' / 'excel'
OUTPUT_DIR = PROJECT_ROOT / 'output'

# Noise (std ~3.7e-4) is ~50x the true per-step slope (~6e-6), so per-step
# thresholding is hopeless. Instead: heavy smoothing, then a forward and a
# backward slope. rising/falling only where both directions agree; where they
# disagree (near a peak/trough) is "holding". Using both directions keeps
# holding centered on the extremum even when the wave is asymmetric.
SMOOTH_WINDOW = 200
SLOPE_SPAN = 130  # forward/backward slope span
SLOPE_RATIO = 0.12  # holding = |slope| below this fraction of the characteristic max slope
# red = rising, green = holding, blue = falling

OUTPUT_DIR.mkdir(exist_ok=True)

for xlsx_path in sorted(glob.glob(str(EXCEL_DIR / '*.xlsx'))):
    name = os.path.splitext(os.path.basename(xlsx_path))[0]
    PLOT_TITLE = f'electric_wave_analysis [{name}]'
    out_base = OUTPUT_DIR / PLOT_TITLE

    # Load data (first two columns: time, amplitude)
    data = pd.read_excel(xlsx_path, header=None).values
    amplitude = data[:, 1].astype(float)
    N = len(amplitude)
    # The recorded time column is irregularly quantized (1-20 samples share a
    # timestamp); rebuild it as a uniform axis over the same range
    time = np.linspace(float(data[0, 0]), float(data[-1, 0]), N)

    # Heavy moving average to recover the underlying wave from the noise
    pad = SMOOTH_WINDOW // 2
    padded = np.pad(amplitude, pad, mode='edge')
    smoothed = np.convolve(padded, np.ones(SMOOTH_WINDOW) / SMOOTH_WINDOW, mode='valid')[:N]

    # Forward and backward slope over SLOPE_SPAN, per original index
    idx = np.arange(N)
    forward = smoothed[np.minimum(idx + SLOPE_SPAN, N - 1)] - smoothed
    backward = smoothed - smoothed[np.maximum(idx - SLOPE_SPAN, 0)]

    # Threshold auto-derived from the data: a fraction of the characteristic max
    # slope (95th percentile, robust to edge spikes)
    threshold = SLOPE_RATIO * np.percentile(np.maximum(np.abs(forward), np.abs(backward)), 95)

    # rising/falling where both directions clearly slope the same way; the flat
    # region near each extremum (slope magnitude below threshold) is holding, so
    # its width follows how flat the data actually is there
    rising = (forward > threshold) & (backward > threshold)
    falling = (forward < -threshold) & (backward < -threshold)
    state = np.where(rising, 'rising', np.where(falling, 'falling', 'holding'))

    # Save state per original index
    with open(f'{out_base}.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['index', 'state'])
        for i, s in enumerate(state):
            writer.writerow([i, s])

    # Plot smoothed waveform: red = rising, green = holding, blue = falling
    plt.figure()
    colors = {'rising': 'red', 'holding': 'green', 'falling': 'blue'}
    for i in range(N - 1):
        plt.plot(time[i:i+2], smoothed[i:i+2], color=colors[state[i]], linewidth=1)

    plt.xlabel('Time (s)')
    plt.ylabel('Amplitude (V)')
    plt.title(PLOT_TITLE)
    plt.grid(True, alpha=0.3)
    plt.savefig(f'{out_base}.png', dpi=150, bbox_inches='tight')
    plt.close()

    print(f'Saved {out_base}.csv ({N} rows)')

    # Length of each consecutive-state segment
    boundaries = np.where(state[1:] != state[:-1])[0] + 1
    segments = np.split(np.arange(N), boundaries)
    for seg in segments:
        print(f'{state[seg[0]]:8s} [{seg[0]:5d}-{seg[-1]:5d}] length={len(seg)}')

    # Classify holding segments by neighbours: after rising = high (peak) hold,
    # after falling = low (trough) hold. Fall back to the next segment if the
    # holding segment is the first one.
    high_holds, low_holds = [], []
    for i, seg in enumerate(segments):
        if state[seg[0]] != 'holding':
            continue
        prev_state = state[segments[i - 1][0]] if i > 0 else None
        next_state = state[segments[i + 1][0]] if i + 1 < len(segments) else None
        kind = prev_state if prev_state in ('rising', 'falling') else next_state
        if kind == 'rising':
            high_holds.append(seg)
        elif kind == 'falling':
            low_holds.append(seg)

    for label, group in (('High (after rising)', high_holds), ('Low  (after falling)', low_holds)):
        if not group:
            continue
        longest = max(group, key=len)
        print(f'{label} longest [{longest[0]:5d}-{longest[-1]:5d}] length={len(longest)} mean={smoothed[longest].mean():.6f}')
