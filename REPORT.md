# Screener Backtest — Strategy Comparison

> DEGRADED-DATA RUN: no delivery/surveillance/calendar data, adjusted OHLCV only.

- **Config hash:** `f4b4e3f7a20e4a4de94970b4d9ad378c03686e60e75893306737484f02b2dcee`  
- **Window:** [None, None]  
- **Universe:** 2715 symbols, 2172 sessions (2018-01-01 → 2026-10-16)  
- **Benchmark (equal-weight B&H):** 0.6755

## Comparison at capital ₹1000

| Strategy | N | WinRate | SafeRate | TailBreach | Expectancy | PF | MaxDD | CAGR | Trades/yr |
|---|---|---|---|---|---|---|---|---|---|
| recovered_after_rej | 1134 | 0.2002 | 0.8519 | 0.1825 | 0.0120 | 1.4130 | - | - | - |
| trend | 156712 | 0.1207 | 0.7804 | 0.2775 | -0.0152 | 0.6220 | - | - | - |
| momentum_top | 6241 | 0.1721 | 0.6360 | 0.4113 | -0.0164 | 0.6610 | - | - | - |
| high_52w | 4689 | 0.1086 | 0.7635 | 0.2856 | -0.0178 | 0.5660 | - | - | - |
| high_effort_low_result | 10311 | 0.1170 | 0.7555 | 0.3108 | -0.0185 | 0.5690 | - | - | - |
| breakout_day | 8831 | 0.1367 | 0.7001 | 0.3628 | -0.0192 | 0.5840 | - | - | - |
| fip_proxy | 11011 | 0.0929 | 0.7872 | 0.2733 | -0.0199 | 0.5120 | - | - | - |
| random | 1692 | 0.0396 | 0.9202 | 0.1093 | -0.0200 | 0.3400 | - | - | - |
| vol_breakout | 20207 | 0.1251 | 0.7187 | 0.3461 | -0.0203 | 0.5530 | - | - | - |
| aae_acceptance | 865 | 0.0751 | 0.5225 | 0.1434 | -0.0221 | 0.4420 | - | - | - |
| trap | 2407 | 0.1936 | 0.4524 | 0.5858 | -0.0275 | 0.5430 | - | - | - |

## Capital sensitivity (₹1000 / ₹10,000 / ₹1,00,000)

| Strategy | Capital | N | Expectancy | WinRate | SafeRate |
|---|---|---|---|---|---|
| aae_acceptance | 1000 | 865 | -0.0221 | 0.0751 | 0.5225 |
| trap | 1000 | 2407 | -0.0275 | 0.1936 | 0.4524 |
| breakout_day | 1000 | 8831 | -0.0192 | 0.1367 | 0.7001 |
| vol_breakout | 1000 | 20207 | -0.0203 | 0.1251 | 0.7187 |
| momentum_top | 1000 | 6241 | -0.0164 | 0.1721 | 0.6360 |
| high_52w | 1000 | 4689 | -0.0178 | 0.1086 | 0.7635 |
| trend | 1000 | 156712 | -0.0152 | 0.1207 | 0.7804 |
| fip_proxy | 1000 | 11011 | -0.0199 | 0.0929 | 0.7872 |
| high_effort_low_result | 1000 | 10311 | -0.0185 | 0.1170 | 0.7555 |
| recovered_after_rej | 1000 | 1134 | 0.0120 | 0.2002 | 0.8519 |
| random | 1000 | 1692 | -0.0200 | 0.0396 | 0.9202 |

## How to read this

- **SafeRate** = fraction of trades that did NOT stop out first (target/time exits).
- **TailBreach** = fraction of trades with a realised net loss worse than −7%.
- **Trap (B1)** is the honest benchmark for the fear: buying stocks already up ≥15%.
- Adjusted OHLCV only; delivery/band/circuit filters are reported as NA, not guessed.
