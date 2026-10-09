# Does the ranking actually rank?

Session range 2020-10-05 to 2026-10-09, 2698 symbols, 2,579,608 scored observations.

## 1. The one-line answer

**The highest-scoring bucket does NOT beat the lowest-scoring one (-0.09% over 20 sessions). The ranking does not order outcomes. Names clearing every gate averaged 0.0161 over 32562 events with a 0.5148 win rate.**

## 2. Score decile vs what actually happened next

| Decile | Events | Mean score | +1d | +5d | +10d | +20d | vs universe |
|---|---|---|---|---|---|---|---|
| **D1** | 253,150 | 0.1854 | 0.0009 | 0.0066 | 0.0142 | 0.0296 | 0.0055 |
| **D2** | 253,150 | 0.3126 | 0.0012 | 0.0067 | 0.0134 | 0.0247 | 0.0006 |
| **D3** | 253,150 | 0.3722 | 0.0011 | 0.0057 | 0.0117 | 0.023 | -0.0012 |
| **D4** | 253,150 | 0.4183 | 0.0011 | 0.0055 | 0.0109 | 0.0216 | -0.0025 |
| **D5** | 253,150 | 0.4583 | 0.001 | 0.0053 | 0.0108 | 0.0216 | -0.0025 |
| **D6** | 253,149 | 0.4958 | 0.001 | 0.0052 | 0.0105 | 0.0216 | -0.0025 |
| **D7** | 253,150 | 0.5337 | 0.0011 | 0.0055 | 0.011 | 0.0225 | -0.0016 |
| **D8** | 253,150 | 0.5745 | 0.0012 | 0.0055 | 0.0111 | 0.0226 | -0.0015 |
| **D9** | 253,150 | 0.6236 | 0.0014 | 0.0063 | 0.0126 | 0.0254 | 0.0012 |
| **D10** | 253,150 | 0.7086 | 0.0015 | 0.0069 | 0.0141 | 0.0287 | 0.0045 |

Universe mean 20-session forward return: **0.024133532801095627**

## 3. The gate verdict -- the screen's strongest claim

| Group | Events | Mean score | +1d | +5d | +10d | +20d | Win rate | Worst-excursion |
|---|---|---|---|---|---|---|---|---|
| **CLEARS every gate** | 32,562 | 0.5753 | 0.0019 | 0.0034 | 0.0073 | 0.0161 | 0.5148 | -0.0874 |
| **does NOT clear** | 2,498,937 | 0.4669 | 0.0011 | 0.006 | 0.0121 | 0.0242 | 0.5044 | -0.085 |

## What this does and does not prove

- Forward returns are outcomes measured after the verdict. Every score was computed from data through its own session, so nothing leaks backwards.
- The gate-clearing group is SMALL and self-selected: those are exactly the sessions where the engine said 'act'. Read the event count before the percentage -- a strong-looking rate on a few dozen events is noise.
- Survivorship is not controlled: the universe is today's listed NSE cash equities, so names that were delisted are absent entirely.
- The score weights were fitted to 5-day forward returns on this same sample. A decile table measured on the fitting sample flatters it; the walk-forward folds in protocol/crosssec.py are the honest comparison.

Forward returns are OUTCOMES. Every score was computed from data through its own session, so no outcome feeds back into a verdict.