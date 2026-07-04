# electric_wave_analysis

파형 데이터에서 상승, 유지, 하강 구간을 나눠 보는 작업 폴더입니다.

## 폴더 구조

```text
electric_wave_analysis/
├─ data/
│  ├─ excel/                  분석에 쓰는 xlsx 파일
│  └─ electric_wave_analysis_data.xlsx  원본 데이터
├─ script/                    분석 스크립트
├─ output/                    분석 결과
├─ electric_wave_analysis_log.md       분석 과정 기록
└─ README.md
```

## 데이터

`data/excel/`에는 측정 조건별 엑셀 파일이 들어 있습니다.

- `Clean`
- `Nothing`
- `Scratch0`
- `Scratch30`
- `Scratch60`
- `Scratch90`

각 파일은 시간과 전압 데이터를 담고 있습니다.

## 스크립트

`script/plot_wave.py`

- 엑셀 데이터를 읽어서 파형을 분석합니다.
- 각 지점을 `rising`, `holding`, `falling`으로 분류합니다.
- 결과 CSV와 PNG를 만듭니다.

`script/hold_std.py`

- holding 구간의 표준편차를 계산합니다.

`script/holding_std.py`

- holding 구간을 자르는 기준을 바꿔가며 표준편차를 비교합니다.

## 결과

`output/`에는 분석 결과가 들어 있습니다.

```text
electric_wave_analysis [파일명].csv
electric_wave_analysis [파일명].png
holding_std.csv
nothing_ratio_sweep.csv
nothing_trim_sweep.csv
```

- `.csv`: 각 인덱스의 상태 분류 결과
- `.png`: 상태별 색으로 표시한 파형 그래프
- `holding_std.csv`: holding 구간 통계
- `nothing_*_sweep.csv`: Nothing 데이터 기준 trim 비교 결과

## 메모

`electric_wave_analysis_log.md`에는 파라미터를 정한 과정과 이전 시행착오가 정리되어 있습니다.
분석 기준을 바꾸기 전에는 이 파일을 먼저 보는 게 좋습니다.

실행 순서는 `실행.md`에 따로 정리했습니다.


