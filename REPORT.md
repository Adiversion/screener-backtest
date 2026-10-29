# Screener Backtest — Strategy Comparison

> DEGRADED-DATA RUN: no delivery/surveillance/calendar data, adjusted OHLCV only.

- **Config hash:** `f4b4e3f7a20e4a4de94970b4d9ad378c03686e60e75893306737484f02b2dcee`  
- **Window:** [None, None]  
- **Universe:** 2727 symbols, 2180 sessions (2018-01-01 → 2026-10-29)  
- **Benchmark (equal-weight B&H):** 0.6570

## Comparison at capital ₹1000

| Strategy | N | WinRate | SafeRate | TailBreach | Expectancy | PF | MaxDD | CAGR | Trades/yr |
|---|---|---|---|---|---|---|---|---|---|
| recovered_after_rej | 1128 | 0.2021 | 0.8493 | 0.1844 | 0.0118 | 1.4050 | - | - | - |
| random | 1677 | 0.0250 | 0.9117 | 0.1032 | -0.0147 | 0.4010 | - | - | - |
| trend | 156430 | 0.1209 | 0.7794 | 0.2784 | -0.0152 | 0.6220 | - | - | - |
| momentum_top | 6257 | 0.1716 | 0.6350 | 0.4125 | -0.0165 | 0.6580 | - | - | - |
| high_52w | 4698 | 0.1088 | 0.7622 | 0.2869 | -0.0179 | 0.5660 | - | - | - |
| high_effort_low_result | 10315 | 0.1168 | 0.7546 | 0.3113 | -0.0185 | 0.5680 | - | - | - |
| breakout_day | 8815 | 0.1368 | 0.6993 | 0.3634 | -0.0192 | 0.5840 | - | - | - |
| fip_proxy | 11019 | 0.0927 | 0.7860 | 0.2743 | -0.0200 | 0.5110 | - | - | - |
| vol_breakout | 20164 | 0.1251 | 0.7175 | 0.3471 | -0.0203 | 0.5520 | - | - | - |
| aae_acceptance | 856 | 0.0748 | 0.5222 | 0.1414 | -0.0221 | 0.4420 | - | - | - |
| trap | 2405 | 0.1929 | 0.4520 | 0.5863 | -0.0277 | 0.5400 | - | - | - |

## Capital sensitivity (₹1000 / ₹10,000 / ₹1,00,000)

| Strategy | Capital | N | Expectancy | WinRate | SafeRate |
|---|---|---|---|---|---|
| aae_acceptance | 1000 | 856 | -0.0221 | 0.0748 | 0.5222 |
| trap | 1000 | 2405 | -0.0277 | 0.1929 | 0.4520 |
| breakout_day | 1000 | 8815 | -0.0192 | 0.1368 | 0.6993 |
| vol_breakout | 1000 | 20164 | -0.0203 | 0.1251 | 0.7175 |
| momentum_top | 1000 | 6257 | -0.0165 | 0.1716 | 0.6350 |
| high_52w | 1000 | 4698 | -0.0179 | 0.1088 | 0.7622 |
| trend | 1000 | 156430 | -0.0152 | 0.1209 | 0.7794 |
| fip_proxy | 1000 | 11019 | -0.0200 | 0.0927 | 0.7860 |
| high_effort_low_result | 1000 | 10315 | -0.0185 | 0.1168 | 0.7546 |
| recovered_after_rej | 1000 | 1128 | 0.0118 | 0.2021 | 0.8493 |
| random | 1000 | 1677 | -0.0147 | 0.0250 | 0.9117 |

## How to read this

- **SafeRate** = fraction of trades that did NOT stop out first (target/time exits).
- **TailBreach** = fraction of trades with a realised net loss worse than −7%.
- **Trap (B1)** is the honest benchmark for the fear: buying stocks already up ≥15%.
- Adjusted OHLCV only; delivery/band/circuit filters are reported as NA, not guessed.
