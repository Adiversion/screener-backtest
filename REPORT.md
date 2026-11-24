# Screener Backtest — Strategy Comparison

> DEGRADED-DATA RUN: no delivery/surveillance/calendar data, adjusted OHLCV only.

- **Config hash:** `f4b4e3f7a20e4a4de94970b4d9ad378c03686e60e75893306737484f02b2dcee`  
- **Window:** [None, None]  
- **Universe:** 2783 symbols, 2197 sessions (2018-01-01 → 2026-11-24)  
- **Benchmark (equal-weight B&H):** 0.6530

## Comparison at capital ₹1000

| Strategy | N | WinRate | SafeRate | TailBreach | Expectancy | PF | MaxDD | CAGR | Trades/yr |
|---|---|---|---|---|---|---|---|---|---|
| recovered_after_rej | 1140 | 0.2009 | 0.8509 | 0.1825 | 0.0119 | 1.4070 | - | - | - |
| trend | 157652 | 0.1204 | 0.7806 | 0.2773 | -0.0152 | 0.6210 | - | - | - |
| momentum_top | 6290 | 0.1714 | 0.6358 | 0.4114 | -0.0164 | 0.6600 | - | - | - |
| high_52w | 4739 | 0.1083 | 0.7641 | 0.2844 | -0.0178 | 0.5670 | - | - | - |
| high_effort_low_result | 10426 | 0.1162 | 0.7560 | 0.3109 | -0.0185 | 0.5680 | - | - | - |
| breakout_day | 8917 | 0.1363 | 0.7018 | 0.3607 | -0.0191 | 0.5840 | - | - | - |
| fip_proxy | 11146 | 0.0928 | 0.7872 | 0.2728 | -0.0198 | 0.5140 | - | - | - |
| vol_breakout | 20430 | 0.1241 | 0.7200 | 0.3445 | -0.0203 | 0.5510 | - | - | - |
| aae_acceptance | 873 | 0.0733 | 0.5269 | 0.1420 | -0.0222 | 0.4380 | - | - | - |
| trap | 2405 | 0.1942 | 0.4511 | 0.5875 | -0.0276 | 0.5420 | - | - | - |
| random | 1538 | 0.0150 | 0.9389 | 0.0826 | -0.0291 | 0.1390 | - | - | - |

## Capital sensitivity (₹1000 / ₹10,000 / ₹1,00,000)

| Strategy | Capital | N | Expectancy | WinRate | SafeRate |
|---|---|---|---|---|---|
| aae_acceptance | 1000 | 873 | -0.0222 | 0.0733 | 0.5269 |
| trap | 1000 | 2405 | -0.0276 | 0.1942 | 0.4511 |
| breakout_day | 1000 | 8917 | -0.0191 | 0.1363 | 0.7018 |
| vol_breakout | 1000 | 20430 | -0.0203 | 0.1241 | 0.7200 |
| momentum_top | 1000 | 6290 | -0.0164 | 0.1714 | 0.6358 |
| high_52w | 1000 | 4739 | -0.0178 | 0.1083 | 0.7641 |
| trend | 1000 | 157652 | -0.0152 | 0.1204 | 0.7806 |
| fip_proxy | 1000 | 11146 | -0.0198 | 0.0928 | 0.7872 |
| high_effort_low_result | 1000 | 10426 | -0.0185 | 0.1162 | 0.7560 |
| recovered_after_rej | 1000 | 1140 | 0.0119 | 0.2009 | 0.8509 |
| random | 1000 | 1538 | -0.0291 | 0.0150 | 0.9389 |

## How to read this

- **SafeRate** = fraction of trades that did NOT stop out first (target/time exits).
- **TailBreach** = fraction of trades with a realised net loss worse than −7%.
- **Trap (B1)** is the honest benchmark for the fear: buying stocks already up ≥15%.
- Adjusted OHLCV only; delivery/band/circuit filters are reported as NA, not guessed.
