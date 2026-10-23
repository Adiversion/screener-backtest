# Screener Backtest — Strategy Comparison

> DEGRADED-DATA RUN: no delivery/surveillance/calendar data, adjusted OHLCV only.

- **Config hash:** `f4b4e3f7a20e4a4de94970b4d9ad378c03686e60e75893306737484f02b2dcee`  
- **Window:** [None, None]  
- **Universe:** 2720 symbols, 2177 sessions (2018-01-01 → 2026-10-23)  
- **Benchmark (equal-weight B&H):** 0.5605

## Comparison at capital ₹1000

| Strategy | N | WinRate | SafeRate | TailBreach | Expectancy | PF | MaxDD | CAGR | Trades/yr |
|---|---|---|---|---|---|---|---|---|---|
| recovered_after_rej | 1127 | 0.2005 | 0.8509 | 0.1828 | 0.0117 | 1.4020 | - | - | - |
| trend | 156377 | 0.1210 | 0.7795 | 0.2784 | -0.0152 | 0.6220 | - | - | - |
| momentum_top | 6247 | 0.1719 | 0.6345 | 0.4125 | -0.0165 | 0.6590 | - | - | - |
| high_52w | 4689 | 0.1090 | 0.7620 | 0.2871 | -0.0179 | 0.5650 | - | - | - |
| high_effort_low_result | 10308 | 0.1170 | 0.7543 | 0.3117 | -0.0186 | 0.5670 | - | - | - |
| breakout_day | 8815 | 0.1370 | 0.6995 | 0.3632 | -0.0191 | 0.5850 | - | - | - |
| fip_proxy | 11003 | 0.0929 | 0.7861 | 0.2745 | -0.0200 | 0.5100 | - | - | - |
| vol_breakout | 20154 | 0.1250 | 0.7174 | 0.3470 | -0.0203 | 0.5520 | - | - | - |
| aae_acceptance | 856 | 0.0748 | 0.5234 | 0.1414 | -0.0220 | 0.4420 | - | - | - |
| trap | 2391 | 0.1945 | 0.4488 | 0.5897 | -0.0277 | 0.5420 | - | - | - |
| random | 1600 | 0.0225 | 0.5906 | 0.4619 | -0.0571 | 0.0800 | - | - | - |

## Capital sensitivity (₹1000 / ₹10,000 / ₹1,00,000)

| Strategy | Capital | N | Expectancy | WinRate | SafeRate |
|---|---|---|---|---|---|
| aae_acceptance | 1000 | 856 | -0.0220 | 0.0748 | 0.5234 |
| trap | 1000 | 2391 | -0.0277 | 0.1945 | 0.4488 |
| breakout_day | 1000 | 8815 | -0.0191 | 0.1370 | 0.6995 |
| vol_breakout | 1000 | 20154 | -0.0203 | 0.1250 | 0.7174 |
| momentum_top | 1000 | 6247 | -0.0165 | 0.1719 | 0.6345 |
| high_52w | 1000 | 4689 | -0.0179 | 0.1090 | 0.7620 |
| trend | 1000 | 156377 | -0.0152 | 0.1210 | 0.7795 |
| fip_proxy | 1000 | 11003 | -0.0200 | 0.0929 | 0.7861 |
| high_effort_low_result | 1000 | 10308 | -0.0186 | 0.1170 | 0.7543 |
| recovered_after_rej | 1000 | 1127 | 0.0117 | 0.2005 | 0.8509 |
| random | 1000 | 1600 | -0.0571 | 0.0225 | 0.5906 |

## How to read this

- **SafeRate** = fraction of trades that did NOT stop out first (target/time exits).
- **TailBreach** = fraction of trades with a realised net loss worse than −7%.
- **Trap (B1)** is the honest benchmark for the fear: buying stocks already up ≥15%.
- Adjusted OHLCV only; delivery/band/circuit filters are reported as NA, not guessed.
