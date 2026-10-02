# Strategies — what we have and how to add one

Every strategy in this engine is a pure function that turns the feature panel
into `TradeSignal`s. **All exits, fees and accounting live in the shared
simulator**, so every strategy is directly comparable: same stop/target/time
logic, same cost model, same metrics.

Registry size today: **29 strategies** across 4 source modules.

Run any subset:

```bash
python scripts/run_backtest.py --strategies all                       # all 29
python scripts/run_backtest.py --strategies protocol                  # the AAE core set
python scripts/run_backtest.py --strategies trap,recovered_after_rej  # explicit list
```

---

## 1. AAE core — `protocol/strategies.py`

| # | Name | Baseline | Entry rule (all evaluated at the D0 close, entry next session's open) |
|---|---|---|---|
| 1 | `aae_acceptance` | AAE | Full 3-state machine: **State 0** breakout (`Close>R20`, `RVOL20≥2.0`, `ClosingRange≥0.60`, `Retention≥0.50`, 20-day base ≤25%, not already extended) → **State 1** acceptance hold within 5 sessions (volume contraction, `Low ≥ R20 − 0.5·ATR`) → **State 2** accepted expansion trigger (`Close >` pullback high, `ClosingRange≥0.5`). Rejected if any of filters F1–F11 fires; candidate only if stop distance ≤ 6%. |
| 2 | `breakout_day` | B2 | `Close>R20` & `RVOL20≥2.0` & `ClosingRange≥0.60` & `Retention≥0.50` (state 0 only, no acceptance wait). |
| 3 | `vol_breakout` | B3 | `Close>R20` & `RVOL20≥1.5`. |
| 4 | `trend` | B6 / M4 | `Close>SMA50>SMA200` & `ret20>0` & `RSI14>50`. |
| 5 | `trap` | B1 | `ret2 ≥ 15%` — buy anything already up ≥15% over two sessions. The honest "fear" baseline. |
| 6 | `high_effort_low_result` | B8 | `RVOL20≥2.5` & `ResultATR≤0.5` (Gervais vs Turtle-Soup cell). |
| 7 | `recovered_after_rej` | B9 | An AAE breakout is **rejected** (closes below R20), then `Close>R20` again within 3 sessions; entry on the reclaim + 1. |
| 8 | `cash` | B0 | Never trades. The no-risk reference. |
| 9 | `random` | B0 (null) | Seeded random (symbol, session); `n=2000` by default. **Anything at or below this row is noise.** |

## 2. Cross-sectional rank baselines — `protocol/strategies_rank.py`

Weekly: the first session of each ISO week per symbol is scored, the top-N are
signalled, entry next session.

| # | Name | Baseline | Score |
|---|---|---|---|
| 10 | `momentum_top` | B4 | 60-day return (`ret60`). |
| 11 | `high_52w` | B5 / M2 | 52-week high proximity `Close/R252`. |
| 12 | `fip_proxy` | B7 | Frog-in-the-Pan proxy: 60-day positive-day frequency (`pos_day_freq60`), restricted to `ret120>0`. |

## 3. PRA — `protocol/strategies_pra.py`

Built on the Pressure→Response→Acceptance event classifier (`protocol/pra.py`).
"Reference" (`R5/R10/R20/R60/R252`) is the challenged swing-high level.

| # | Name | Rule |
|---|---|---|
| 13 | `pra_strong_retention` | `STRONG_RETENTION` events (penetrated R, closed above R, retention ≥ 0.60). |
| 14 | `pra_expansion_attempt` | `EXPANSION_ATTEMPT` events (penetrated R, closed back below R) with `RVOL20 ≥ 1.5`. |
| 15 | `pra_high_effort_low_result` | `HIGH_EFFORT_LOW_RESULT` events (high volume, little displacement). |
| 16 | `pra_full` | The full ablation model: `STRONG_RETENTION` **and** `RVOL20≥1.5` **and** `ResultATR≥0.5` **and** `Retention≥0.5` **and** `ClosingRange≥0.5`. |
| 17–20 | `pra_retention_r5`, `pra_retention_r10`, `pra_retention_r60`, `pra_retention_r252` | `STRONG_RETENTION` measured against reference levels R5 / R10 / R60 / R252 (the `gpt 6 astar search max.txt` requirement to register each reference as a separate variant). The R20 case *is* `pra_strong_retention`. |

## 4. Price-Acceptance states + community scanners — `protocol/strategies_pa.py`

These apply the PDF's **liquidity gate** (`liquidity:` in the config —
≥ ₹5 crore 20-day turnover, price > ₹20, ≥ 252 sessions of history).

| # | Name | Family | Rule |
|---|---|---|---|
| 21 | `pa_state_a` | PA state A | **Accepted Expansion**: penetrated R, `Close>R`, `Retention≥0.60`, `ClosingRange≥0.50`. |
| 22 | `pa_state_b` | PA state B | **Pending Acceptance**: penetrated R, `Close>R`, but retention/closing range not yet confirmed. |
| 23 | `pa_state_c` | PA state C | **Rejection / Recovery Pending**: closed slightly below R with a still-decent close. |
| 24 | `pa_state_d` | PA state D | **Failed Acceptance**: penetrated R, surrendered it, closed near the low. A deliberate *failure control* — negative expectancy is the expected, correct result. |
| 25 | `m1_momentum_composite` | M1 | Weekly top-N of the equal-weight `(ret20+ret60+ret120)/3`. |
| 26 | `n1_eod_momentum` | N1 | `Gap≥1%` & `RVOL20≥1.5` & `Close>R20` & rising `ATR14` & `Close>Close[-5]`. |
| 27 | `n2_consolidation_breakout` | N2 | Prior 10-session band ≤ 8% of close & `Close>R10` & `RVOL20≥1.2`. |
| 28 | `n3_absorption` | N3 | `RVOL20≥2.0` & `ResultATR≤0.5` & `Close ≥ 0.98·R20`. |
| 29 | `n4_effort_result_discrepancy` | N4 | `RVOL20≥2.0` & `ClosingRange≤0.35` — Wyckoff "effort without result". |

---

# How to add a new strategy

**Five steps. Nothing else in the engine needs touching.**

### Step 1 — write the builder

Open the module that matches the family, or make a new
`protocol/strategies_<family>.py`:

```python
# protocol/strategies_mine.py
from __future__ import annotations

import numpy as np
import pandas as pd

from protocol.signals import TradeSignal
from protocol.strategies import register


@register("my_pullback")                       # <- the name you'll pass to --strategies
def my_pullback(panel: dict[str, pd.DataFrame], cfg: dict) -> list[TradeSignal]:
    """Buy the first close above R20 after a 3-day pullback, RVOL only 1.2."""
    min_rvol = (cfg.get("strategies", {}).get("my_pullback", {})).get("rvol_min", 1.2)
    out: list[TradeSignal] = []
    for symbol, feat in panel.items():
        d = feat.reset_index(drop=True)
        if len(d) < 25:
            continue
        pullback = d["Close"] < d["R20"]                    # vectorised condition
        signal_day = (d["Close"] > d["R20"]) & (d["rvol20"] >= min_rvol) & pullback.shift(1)
        for i in np.where(signal_day.fillna(False).to_numpy())[0]:
            i = int(i)
            if i + 1 >= len(d):
                continue
            out.append(TradeSignal(
                strategy="my_pullback",
                symbol=symbol,
                signal_date=d["Date"].iloc[i],       # decision bar
                entry_date=d["Date"].iloc[i + 1],    # next session's open
                expected_entry=float(d["Close"].iloc[i]),
                stop_pct=0.07,                       # or stop=... for a structural stop
                meta={"rvol": float(d["rvol20"].iloc[i])},
            ))
    return out
```

Rules of the road:

- **Signals only.** Never compute fees, exits or P&L — the simulator does that.
- **`signal_date < entry_date`, always.** Use the next session's open.
- **Only columns with date ≤ T.** No `shift(-1)`, no `center=True`, no `bfill` —
  `protocol/audit.py` will fail the run and the static scan forbids those strings
  anywhere in `protocol/`.
- **Prefer vectorised conditions**; they are 10–100× faster on the 500-symbol
  universe.

### Step 2 — register the import

`protocol/__init__.py`:

```python
from protocol import strategies_mine as _mine  # noqa: F401 (registers my strategies)
```

(Miss this and `--strategies my_pullback` will report `unknown strategy`.)

### Step 3 — add parameters (optional but recommended)

`config/protocol_v2.yaml`:

```yaml
strategies:
  my_pullback:
    rvol_min: 1.2
```

Now it is tweakable with no code edit:

```bash
python scripts/run_backtest.py --strategies my_pullback --set strategies.my_pullback.rvol_min=1.8
```

> Editing the YAML changes the config hash. Discovery runs freeze it; validation
> runs refuse a changed hash unless you pass `--exploratory`.

### Step 4 — test it

`tests/test_mine.py` — build a small synthetic frame, call the builder, assert
the signals:

```python
import pandas as pd
from protocol.config import load_config
from protocol.features import build_features
from protocol.strategies import REGISTRY

def test_registered():
    assert "my_pullback" in REGISTRY

def test_fires_only_on_pullback_reclaim():
    ...  # build bars, build_features, REGISTRY["my_pullback"]({"X": feat}, load_config())
```

```bash
python -m unittest discover -s tests
```

### Step 5 — run and compare

```bash
python scripts/run_backtest.py --strategies my_pullback,random,trap --capital 1000
```

Open `reports/REPORT.html`. Compare against **`random`** (the honest null) —
if your strategy does not clear it, it is noise.

---

## Useful feature columns

From `protocol/features.py` (every one uses data ≤ T):

`atr14`, `atrpct`, `rvol20` (vs trailing 20-session mean), `result_atr`,
`dir_result`, `closing_range`, `body_eff`, `efficiency`, `R5`, `R10`, `R20`,
`R60`, `R252`, `penetration`, `closing_disp`, `retention`, `ema20`, `extension`,
`ret2`, `ret20`, `ret60`, `ret120`, `prox52`, `pos_day_freq60`, `turnover20`,
and the delivery columns (`deliv_pct`, `deliv_pct_rel`, …) which are currently
always `NaN` because the free data feed has no delivery data.

## Ablations instead of new strategies

To test whether a filter is doing the work, disable it rather than writing a
new strategy:

```bash
python scripts/run_backtest.py --strategies aae_acceptance --set filters.disabled='[F1,F5]'
```

## House style (enforced)

- **No source file over 300 lines** (parent repo `AGENTS.md` rule).
- ONE responsibility per module; thresholds only in `config/protocol_v2.yaml`.
- Keep the strategy registry the single place strategies are registered.
