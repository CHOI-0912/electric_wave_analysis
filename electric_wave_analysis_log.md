# electric_wave_analysis 신호 분석 프로젝트 전체 기록

> 노이즈에 묻힌 주기 파형에서 추세(상승/유지/하강)를 추출하는 DSP 파이프라인.
> 이 문서는 분석 과정 전체를 시간순으로 기록한다 (Claude Desktop 분석용).

---

## 1. 프로젝트 개요

- **목표**: `electric_wave_analysis`의 파형 데이터를 구간별로 분류 — 상승(rising) / 유지(holding) / 하강(falling)
- **산출물**: `plot_wave.py` (분석 스크립트), `wave_analysis.csv` (인덱스별 상태), `wave_analysis.png` (색상 구분 그래프)
- **성격**: 대학 사이드 프로젝트 (디지털 신호처리 / 계측공학)

---

## 2. 입력 데이터 (`electric_wave_analysis`)

| 항목 | 값 |
|---|---|
| 행 수 | 10,000 |
| 열 수 | 2 (헤더 없음) |
| 1열 | 시간 (s), 범위 -2.5e-3 ~ +2.5e-3 |
| 2열 | 진폭 (V), 범위 1.67e-3 ~ 9.67e-3 |
| 파일 크기 | ~190 KB |

### 2.1 데이터의 핵심 특성 (분석으로 밝혀낸 것)

- **진폭 양자화**: 서로 다른 값이 **25개뿐**, 간격 ~3.3e-4 → ADC 양자화 흔적
- **시간축 불규칙 양자화**: 서로 다른 타임스탬프 2,501개, 한 타임스탬프에 **1~20개 샘플**이 몰림, 간격이 5e-7 ~ 1e-5로 들쭉날쭉
- **신호 형태**: 주기 ~2,000 샘플(1ms)의 주기 파형, 전체 구간에 **5주기**. 비대칭(상승/하강 기울기가 다름)
- **노이즈가 신호를 압도**:
  - 원본 per-step 변화량 |dy|: 평균 4.70e-4, 중앙값 3.40e-4, 최대 3.67e-3
  - 노이즈 std (101점 이동평균 잔차): **3.66e-4**
  - 실제 신호의 per-step 기울기 (201점 평활 후): 평균 **5.88e-6**, 최대 1.99e-5
  - → **노이즈가 실제 기울기의 약 50~60배**

---

## 3. 작업 타임라인 (요청 → 대응)

### 단계 0 — 초기 탐색
- `electric_wave_analysis` 구조 파악 후, 사용자가 일단 중지 요청.

### 단계 1 — 1차 정의: per-step 변화량 임계값
- **요청**: "한 time step당 `interval` 이상의 변화"가 나는 구간 = 증가 구간. 증가=빨강, 아니면=파랑.
- **확정 사항**: `interval`은 특정 값으로 지정, 변화 기준은 **절댓값** 변화.
- `interval = 0.0001`로 시작.
- 1차 그래프 생성 (당시엔 서브플롯 2개 + 통계 출력 포함).

### 단계 2 — 슬라이딩 윈도우 도입
- **요청**: 노이즈 때문에 잘 안 나옴 → `n, n+1, n+2` 평균(슬라이딩 window=3) 적용 후 `interval` 판정. '구간' 여부를 True/False로, **원래 인덱스에 맞게** CSV로 저장.
- **CLAUDE.md 기반 수정**:
  - 버그: 윈도우가 `n-1, n, n+1`로 잘못됨 → `n, n+1, n+2`로 수정 (`np.convolve(..., mode='valid')`)
  - speculative 제거: CSV의 불필요한 컬럼(time/amplitude/smoothed) 삭제, 변화량 서브플롯·통계 출력 삭제, pandas 의존성 제거
- `interval`은 사용자가 파일에서 0.0005로 변경.

### 단계 3 — 윈도우 크기 실험
- window 3 → 5 → 10 순차 변경. 여전히 노이즈로 분류가 불안정.

### 단계 4 — "노이즈가 너무 강하다, 알아서 분석" → 방법론 전환
- **정량 분석으로 per-step 임계값 방식이 근본적으로 불가능함을 증명**:
  - 노이즈 std 3.66e-4 vs 실제 기울기 6e-6 → 50배
  - W=800 이동평균을 해도 per-step 기울기 부호가 **534번** 뒤집힘
- **새 방법**: 강한 평활(W=200) → 넓은 span(L=300)에 걸친 기울기의 **부호**로 상승/하강 판정
  - 결과: 9개 전이점, 상승 5 / 하강 5 깨끗하게 분리, 전이 간격 ~1,000 샘플

### 단계 5 — 3구간으로 확장 (하강 / 유지 / 상승)
- **요청**: 구간을 3개로.
- span-slope 임계값 분포 분석 후, 사용자가 임계값 **1e-3 (유지 ~13%)** 선택.

### 단계 6 — "유지 구간이 왼쪽으로 쏠림" 문제
- **증상**: 초록(유지)이 피크 왼쪽은 잘 잡는데 오른쪽이 끊김.
- **원인 진단**: 파형이 비대칭(상승 완만, 하강 급함)이라, **centered span-slope의 영점이 실제 극점보다 왼쪽**에 생김.
  - 측정: span-slope 영점 `[825,1821,2834,...]` vs 실제 극점(argmax/argmin) `[938,1916,2929,...]` → **+75~+113 샘플 오른쪽으로 어긋남**

### 단계 7 — 양방향(forward/backward) 방식 (사용자 제안)
- **요청**: "양방향으로 window 한 다음 공통지점으로".
- **구현**:
  - `forward = smoothed[i+span] - smoothed[i]` (미래 추세)
  - `backward = smoothed[i] - smoothed[i-span]` (과거 추세)
  - 둘 다 양수 → 상승 / 둘 다 음수 → 하강 / 부호 불일치 → 유지
- **검증**: 유지 블록 중심 ↔ 실제 극점 편차가 **-22 ~ +2 샘플**로 개선 (기존 -75~-113)
- `SLOPE_SPAN = 130` 채택. 이때 유지 길이는 **모두 정확히 130**.

### 단계 8 — "모든 유지 길이가 130인 건 비현실적" → 데이터 적응형으로
- **수학적 사실**: 봉우리를 두 직선의 꺾임으로 보면 유지 폭이 좌우 기울기와 무관하게 **정확히 span**이 됨 → 데이터 특성 미반영.
- **요청**: "데이터 특성에 맞게 알아서". "평탄함"의 정의로 사용자가 **기울기 크기** 선택.
- **구현**:
  - 자동 임계값 `threshold = SLOPE_RATIO × (기울기 크기의 95퍼센타일)`
  - 95퍼센타일 사용 이유: `max()`는 엣지 스파이크에 취약 → 강건한 대표값
  - 상승: `forward > +threshold & backward > +threshold`
  - 하강: `forward < -threshold & backward < -threshold`
  - 유지: 그 외 (부호 불일치 + 기울기가 완만한 구간)
  - `SLOPE_RATIO = 0.12`
- **결과**: 유지 길이가 **171~204로 데이터에 따라 변동** (더 이상 고정 아님).

### 단계 9 — 출력/가독성 개선
- 각 연속 구간의 `[시작-끝] length` 콘솔 출력 추가.
- 그래프 제목을 상단 상수 `PLOT_TITLE`로 분리.

### 단계 10 — 시간축 수정
- **증상**: Time 축이 이상함.
- **원인**: CSV 시간 열이 불규칙 양자화(1~20 샘플/타임스탬프, 간격 5e-7~1e-5) → x축 왜곡.
- **수정**: 시간 열을 그대로 쓰지 않고 동일 범위에 균일 간격으로 재생성 — `np.linspace(data[0,0], data[-1,0], N)`.
- (사용자가 "가장 왼쪽을 0으로" 요청 후 곧 롤백 → 현재는 원래 범위 -0.0025~0.0025 유지.)

---

## 4. 최종 알고리즘 (개조식)

1. **데이터 로드**: `electric_wave_analysis`에서 진폭(2열)만 사용. 시간축은 균일 간격으로 재생성.
2. **노이즈 제거**: 200점 이동평균(FIR 저역통과 필터) → `smoothed`. 엣지는 `np.pad(mode='edge')`로 처리.
3. **양방향 기울기**:
   - `forward = smoothed[i+130] - smoothed[i]`
   - `backward = smoothed[i] - smoothed[i-130]`
   - (130은 평균 윈도우가 아니라 **두 점 사이 거리**. 130으로 나누지 않음 — 부호/상대크기만 필요)
4. **자동 임계값**: `threshold = 0.12 × percentile(max(|forward|,|backward|), 95)`
5. **3-state 분류**:
   - 상승 = forward·backward 둘 다 `> +threshold`
   - 하강 = 둘 다 `< -threshold`
   - 유지 = 그 외
6. **출력**: CSV(인덱스별 state), PNG(색상 그래프), 콘솔(구간 길이).

---

## 5. 파라미터

| 상수 | 현재값 | 의미 | 조절 효과 |
|---|---|---|---|
| `SMOOTH_WINDOW` | 200 | 이동평균 윈도우 | 클수록 노이즈 제거 강함, 위상 지연·왜곡 증가 |
| `SLOPE_SPAN` | 130 | forward/backward 기울기 측정 거리 | 클수록 기울기 부호 안정, 극점 부근 분해능 저하 |
| `SLOPE_RATIO` | 0.12 | 유지 판정 임계 비율 | 클수록 유지 구간 넓어짐. **0.2 이상은 상승/하강 중간이 잘게 쪼개짐(주의)** |
| `PLOT_TITLE` | 문자열 | 그래프 제목 | — |

---

## 6. 최종 출력 결과

### 6.1 구간 분류 결과 (콘솔 출력)

```
holding  [    0-   60] length=61      ← 엣지 (데이터 경계 잘림)
falling  [   61-  811] length=751
holding  [  812- 1015] length=204
rising   [ 1016- 1812] length=797
holding  [ 1813- 1989] length=177
falling  [ 1990- 2823] length=834
holding  [ 2824- 3016] length=193
rising   [ 3017- 3785] length=769
holding  [ 3786- 3985] length=200
falling  [ 3986- 4824] length=839
holding  [ 4825- 5014] length=190
rising   [ 5015- 5821] length=807
holding  [ 5822- 6000] length=179
falling  [ 6001- 6829] length=829
holding  [ 6830- 7017] length=188
rising   [ 7018- 7835] length=818
holding  [ 7836- 8006] length=171
falling  [ 8007- 8824] length=818
holding  [ 8825- 9015] length=191
rising   [ 9016- 9814] length=799
holding  [ 9815- 9999] length=185      ← 엣지
```

- 유지 길이: 171, 177, 179, 185, 188, 190, 191, 193, 200, 204 (+ 엣지 61) — **데이터에 따라 변동**
- 상승/하강 길이: ~751~839
- 패턴: falling ↔ holding ↔ rising ↔ holding 반복 (주기성 확인)

### 6.2 분석 과정에서 측정된 핵심 수치

| 측정 항목 | 값 |
|---|---|
| 노이즈 std (101-MA 잔차) | 3.66e-4 |
| 실제 per-step 기울기 (201-MA) | 평균 5.88e-6 / 최대 1.99e-5 |
| 노이즈/신호 비 | 약 50~60배 |
| 신호 주기 (FFT) | 2,000 샘플 = 1 ms, 5주기 |
| W=800 평활 후에도 per-step 기울기 부호 뒤집힘 | 534회 |
| span-slope 영점 vs 실제 극점 어긋남 | +75 ~ +113 샘플 |
| 양방향 방식 유지블록 중심 오차 | -22 ~ +2 샘플 |
| 기울기 크기 95퍼센타일 (max 방향) | 1.51e-3 |

---

## 7. 최종 코드 (`plot_wave.py`)

```python
import numpy as np
import matplotlib.pyplot as plt
import csv

# Noise (std ~3.7e-4) is ~50x the true per-step slope (~6e-6), so per-step
# thresholding is hopeless. Instead: heavy smoothing, then a forward and a
# backward slope. rising/falling only where both directions agree; where they
# disagree (near a peak/trough) is "holding". Using both directions keeps
# holding centered on the extremum even when the wave is asymmetric.
SMOOTH_WINDOW = 200
SLOPE_SPAN = 130  # forward/backward slope span
SLOPE_RATIO = 0.12  # holding = |slope| below this fraction of the characteristic max slope
PLOT_TITLE = f'electric_wave_analysis [Clean (2)]'
# red = rising, green = holding, blue = falling
# Load data
data = np.loadtxt('electric_wave_analysis.csv', delimiter=',')
amplitude = data[:, 1]
N = len(amplitude)
# The recorded time column is irregularly quantized (1-20 samples share a
# timestamp); rebuild it as a uniform axis over the same range
time = np.linspace(data[0, 0], data[-1, 0], N)

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
with open('wave_analysis.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['index', 'state'])
    for i, s in enumerate(state):
        writer.writerow([i, s])

# Plot smoothed waveform: red = rising, green = holding, blue = falling
colors = {'rising': 'red', 'holding': 'green', 'falling': 'blue'}
for i in range(N - 1):
    plt.plot(time[i:i+2], smoothed[i:i+2], color=colors[state[i]], linewidth=1)

plt.xlabel('Time (s)')
plt.ylabel('Amplitude (V)')
plt.title(PLOT_TITLE)
plt.grid(True, alpha=0.3)
plt.savefig('wave_analysis.png', dpi=150, bbox_inches='tight')
plt.show()

print(f'Saved wave_analysis.csv ({N} rows)')

# Length of each consecutive-state segment
boundaries = np.where(state[1:] != state[:-1])[0] + 1
segments = np.split(np.arange(N), boundaries)
for seg in segments:
    print(f'{state[seg[0]]:8s} [{seg[0]:5d}-{seg[-1]:5d}] length={len(seg)}')
```

---

## 8. 알려진 한계 / 개선 여지

- **이동평균의 위상 지연**: FIR 이동평균은 위상 지연·엣지 왜곡이 있음. Savitzky-Golay 필터가 추세 보존에 더 유리할 수 있음.
- **`SLOPE_RATIO`는 여전히 경험적**: 0.12는 이 데이터에 맞춘 값. 완전 자동화하려면 Otsu 등 분포 기반 임계값 고려.
- **엣지 처리**: 양 끝 구간(인덱스 0 근처, 9999 근처)은 데이터 경계 잘림으로 짧은 조각이 생김.
- **`SLOPE_RATIO` 과대 시 파편화**: 0.2 이상이면 상승/하강 중간에 길이 1짜리 유지 조각이 다수 생김.
- **시간축 정보 손실**: 원본 시간 열을 버리고 균일 간격으로 재생성함 (원본이 불규칙 양자화라 불가피했으나, 실제 샘플링이 균일하다는 가정에 의존).
- **주파수 영역 미분석**: FFT로 주기(2000샘플)만 확인. 본격적인 스펙트럼 분석은 안 함.

---

## 9. 학술적 맥락 (과목 매핑)

| 과목 | 이 프로젝트에서의 대응 |
|---|---|
| **디지털 신호처리 (DSP)** | 이동평균 = FIR 저역통과 필터 / forward·backward 기울기 = 수치 미분(차분) / 윈도우↔지연 트레이드오프 |
| **계측공학 / 센서및계측** | 오실로스코프류 시간영역 파형 / ADC 양자화(진폭 25레벨, 시간축 불규칙) / SNR·노이즈 플로어 특성화 |
| **수치해석** | 유한차분 미분 |
| **데이터분석 / 통계** | 퍼센타일 기반 자동 임계값 |

### 보고서 작성 시 강조 포인트
- **"측정 먼저, 설계 나중"**: 노이즈 std vs 실제 기울기를 정량화(50배)하여 naive 방식이 왜 실패하는지 *수치로 증명*.
- **데이터 기반 자동 임계값**: 하드코딩 대신 95퍼센타일 비율 → 다른 데이터로 일반화 가능.
- **실패-진단-수정 서사**: span 방식 → 비대칭 편향 발견 → 양방향 보정. 반복 개선 과정 자체가 가치.
- **용어 학술화**: 이동평균→FIR 저역통과 필터, 130칸 기울기→전후방 차분 미분, 부호+임계값→히스테리시스 기반 상태 분류, 유지 구간→정상상태(steady-state) 검출.


