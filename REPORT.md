# Screener Backtest — Strategy Comparison

> DEGRADED-DATA RUN: no delivery/surveillance/calendar data, adjusted OHLCV only.

- **Config hash:** `f4b4e3f7a20e4a4de94970b4d9ad378c03686e60e75893306737484f02b2dcee`  
- **Window:** [None, None]  
- **Universe:** 2697 symbols, 2167 sessions (2018-01-01 → 2026-10-09)  
- **Benchmark (equal-weight B&H):** 0.6648

## Comparison at capital ₹1000

| Strategy | N | WinRate | SafeRate | TailBreach | Expectancy | PF | MaxDD | CAGR | Trades/yr |
|---|---|---|---|---|---|---|---|---|---|
| recovered_after_rej | 1133 | 0.2021 | 0.8535 | 0.1801 | 0.0122 | 1.4210 | - | - | - |
| trend | 156593 | 0.1208 | 0.7804 | 0.2775 | -0.0152 | 0.6230 | - | - | - |
| momentum_top | 6232 | 0.1723 | 0.6361 | 0.4108 | -0.0163 | 0.6630 | - | - | - |
| high_52w | 4681 | 0.1085 | 0.7639 | 0.2848 | -0.0177 | 0.5680 | - | - | - |
| high_effort_low_result | 10300 | 0.1169 | 0.7553 | 0.3112 | -0.0185 | 0.5680 | - | - | - |
| breakout_day | 8825 | 0.1368 | 0.7003 | 0.3626 | -0.0192 | 0.5840 | - | - | - |
| fip_proxy | 10994 | 0.0930 | 0.7871 | 0.2734 | -0.0199 | 0.5120 | - | - | - |
| vol_breakout | 20202 | 0.1251 | 0.7184 | 0.3462 | -0.0203 | 0.5520 | - | - | - |
| aae_acceptance | 862 | 0.0742 | 0.5232 | 0.1439 | -0.0221 | 0.4410 | - | - | - |
| trap | 2408 | 0.1931 | 0.4510 | 0.5872 | -0.0276 | 0.5420 | - | - | - |
| random | 1629 | 0.0270 | 0.8619 | 0.1835 | -0.0322 | 0.1830 | - | - | - |

## Capital sensitivity (₹1000 / ₹10,000 / ₹1,00,000)

| Strategy | Capital | N | Expectancy | WinRate | SafeRate |
|---|---|---|---|---|---|
| aae_acceptance | 1000 | 862 | -0.0221 | 0.0742 | 0.5232 |
| trap | 1000 | 2408 | -0.0276 | 0.1931 | 0.4510 |
| breakout_day | 1000 | 8825 | -0.0192 | 0.1368 | 0.7003 |
| vol_breakout | 1000 | 20202 | -0.0203 | 0.1251 | 0.7184 |
| momentum_top | 1000 | 6232 | -0.0163 | 0.1723 | 0.6361 |
| high_52w | 1000 | 4681 | -0.0177 | 0.1085 | 0.7639 |
| trend | 1000 | 156593 | -0.0152 | 0.1208 | 0.7804 |
| fip_proxy | 1000 | 10994 | -0.0199 | 0.0930 | 0.7871 |
| high_effort_low_result | 1000 | 10300 | -0.0185 | 0.1169 | 0.7553 |
| recovered_after_rej | 1000 | 1133 | 0.0122 | 0.2021 | 0.8535 |
| random | 1000 | 1629 | -0.0322 | 0.0270 | 0.8619 |

## How to read this

- **SafeRate** = fraction of trades that did NOT stop out first (target/time exits).
- **TailBreach** = fraction of trades with a realised net loss worse than −7%.
- **Trap (B1)** is the honest benchmark for the fear: buying stocks already up ≥15%.
- Adjusted OHLCV only; delivery/band/circuit filters are reported as NA, not guessed.
