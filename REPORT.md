# Screener Backtest — Strategy Comparison

> DEGRADED-DATA RUN: no delivery/surveillance/calendar data, adjusted OHLCV only.

- **Config hash:** `f4b4e3f7a20e4a4de94970b4d9ad378c03686e60e75893306737484f02b2dcee`  
- **Window:** [None, None]  
- **Universe:** 2768 symbols, 2186 sessions (2018-01-01 → 2026-11-06)  
- **Benchmark (equal-weight B&H):** 0.6783

## Comparison at capital ₹1000

| Strategy | N | WinRate | SafeRate | TailBreach | Expectancy | PF | MaxDD | CAGR | Trades/yr |
|---|---|---|---|---|---|---|---|---|---|
| recovered_after_rej | 1138 | 0.2012 | 0.8515 | 0.1819 | 0.0120 | 1.4150 | - | - | - |
| random | 1630 | 0.0393 | 0.9098 | 0.1190 | -0.0139 | 0.5030 | - | - | - |
| trend | 157110 | 0.1206 | 0.7800 | 0.2779 | -0.0152 | 0.6210 | - | - | - |
| momentum_top | 6265 | 0.1716 | 0.6346 | 0.4128 | -0.0165 | 0.6590 | - | - | - |
| high_52w | 4714 | 0.1082 | 0.7630 | 0.2855 | -0.0178 | 0.5670 | - | - | - |
| high_effort_low_result | 10383 | 0.1162 | 0.7554 | 0.3110 | -0.0185 | 0.5680 | - | - | - |
| breakout_day | 8875 | 0.1366 | 0.7006 | 0.3619 | -0.0191 | 0.5840 | - | - | - |
| fip_proxy | 11095 | 0.0926 | 0.7865 | 0.2736 | -0.0199 | 0.5120 | - | - | - |
| vol_breakout | 20311 | 0.1247 | 0.7190 | 0.3453 | -0.0202 | 0.5530 | - | - | - |
| aae_acceptance | 863 | 0.0753 | 0.5261 | 0.1437 | -0.0220 | 0.4430 | - | - | - |
| trap | 2442 | 0.1904 | 0.4554 | 0.5835 | -0.0278 | 0.5370 | - | - | - |

## Capital sensitivity (₹1000 / ₹10,000 / ₹1,00,000)

| Strategy | Capital | N | Expectancy | WinRate | SafeRate |
|---|---|---|---|---|---|
| aae_acceptance | 1000 | 863 | -0.0220 | 0.0753 | 0.5261 |
| trap | 1000 | 2442 | -0.0278 | 0.1904 | 0.4554 |
| breakout_day | 1000 | 8875 | -0.0191 | 0.1366 | 0.7006 |
| vol_breakout | 1000 | 20311 | -0.0202 | 0.1247 | 0.7190 |
| momentum_top | 1000 | 6265 | -0.0165 | 0.1716 | 0.6346 |
| high_52w | 1000 | 4714 | -0.0178 | 0.1082 | 0.7630 |
| trend | 1000 | 157110 | -0.0152 | 0.1206 | 0.7800 |
| fip_proxy | 1000 | 11095 | -0.0199 | 0.0926 | 0.7865 |
| high_effort_low_result | 1000 | 10383 | -0.0185 | 0.1162 | 0.7554 |
| recovered_after_rej | 1000 | 1138 | 0.0120 | 0.2012 | 0.8515 |
| random | 1000 | 1630 | -0.0139 | 0.0393 | 0.9098 |

## How to read this

- **SafeRate** = fraction of trades that did NOT stop out first (target/time exits).
- **TailBreach** = fraction of trades with a realised net loss worse than −7%.
- **Trap (B1)** is the honest benchmark for the fear: buying stocks already up ≥15%.
- Adjusted OHLCV only; delivery/band/circuit filters are reported as NA, not guessed.
