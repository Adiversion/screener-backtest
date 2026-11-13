# Screener Backtest — Strategy Comparison

> DEGRADED-DATA RUN: no delivery/surveillance/calendar data, adjusted OHLCV only.

- **Config hash:** `f4b4e3f7a20e4a4de94970b4d9ad378c03686e60e75893306737484f02b2dcee`  
- **Window:** [None, None]  
- **Universe:** 2761 symbols, 2191 sessions (2018-01-01 → 2026-11-13)  
- **Benchmark (equal-weight B&H):** 0.6867

## Comparison at capital ₹1000

| Strategy | N | WinRate | SafeRate | TailBreach | Expectancy | PF | MaxDD | CAGR | Trades/yr |
|---|---|---|---|---|---|---|---|---|---|
| recovered_after_rej | 1138 | 0.2021 | 0.8515 | 0.1819 | 0.0122 | 1.4220 | - | - | - |
| trend | 157023 | 0.1203 | 0.7800 | 0.2779 | -0.0153 | 0.6210 | - | - | - |
| momentum_top | 6279 | 0.1717 | 0.6348 | 0.4126 | -0.0165 | 0.6590 | - | - | - |
| high_52w | 4723 | 0.1082 | 0.7637 | 0.2846 | -0.0177 | 0.5680 | - | - | - |
| high_effort_low_result | 10395 | 0.1160 | 0.7560 | 0.3103 | -0.0184 | 0.5690 | - | - | - |
| breakout_day | 8895 | 0.1359 | 0.7016 | 0.3610 | -0.0191 | 0.5840 | - | - | - |
| fip_proxy | 11107 | 0.0921 | 0.7866 | 0.2738 | -0.0199 | 0.5110 | - | - | - |
| vol_breakout | 20354 | 0.1243 | 0.7197 | 0.3448 | -0.0202 | 0.5520 | - | - | - |
| random | 1629 | 0.0344 | 0.9362 | 0.0859 | -0.0208 | 0.3170 | - | - | - |
| aae_acceptance | 870 | 0.0713 | 0.5276 | 0.1414 | -0.0225 | 0.4290 | - | - | - |
| trap | 2427 | 0.1924 | 0.4541 | 0.5847 | -0.0276 | 0.5410 | - | - | - |

## Capital sensitivity (₹1000 / ₹10,000 / ₹1,00,000)

| Strategy | Capital | N | Expectancy | WinRate | SafeRate |
|---|---|---|---|---|---|
| aae_acceptance | 1000 | 870 | -0.0225 | 0.0713 | 0.5276 |
| trap | 1000 | 2427 | -0.0276 | 0.1924 | 0.4541 |
| breakout_day | 1000 | 8895 | -0.0191 | 0.1359 | 0.7016 |
| vol_breakout | 1000 | 20354 | -0.0202 | 0.1243 | 0.7197 |
| momentum_top | 1000 | 6279 | -0.0165 | 0.1717 | 0.6348 |
| high_52w | 1000 | 4723 | -0.0177 | 0.1082 | 0.7637 |
| trend | 1000 | 157023 | -0.0153 | 0.1203 | 0.7800 |
| fip_proxy | 1000 | 11107 | -0.0199 | 0.0921 | 0.7866 |
| high_effort_low_result | 1000 | 10395 | -0.0184 | 0.1160 | 0.7560 |
| recovered_after_rej | 1000 | 1138 | 0.0122 | 0.2021 | 0.8515 |
| random | 1000 | 1629 | -0.0208 | 0.0344 | 0.9362 |

## How to read this

- **SafeRate** = fraction of trades that did NOT stop out first (target/time exits).
- **TailBreach** = fraction of trades with a realised net loss worse than −7%.
- **Trap (B1)** is the honest benchmark for the fear: buying stocks already up ≥15%.
- Adjusted OHLCV only; delivery/band/circuit filters are reported as NA, not guessed.
