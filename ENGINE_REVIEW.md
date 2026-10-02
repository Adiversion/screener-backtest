# Engine Review — NSE Stock-Picking Backtest

**Purpose of this document.** It is a complete, deliberately sceptical description of
the engine at `Adiversion/screener-backtest`, written so that a second AI with web
access can **independently check every claim** and find what is wrong. It is not a
promotional summary. Section 9 lists my own errors, several of which changed the
conclusion. Section 10 lists what I could not test.

If you are reviewing this: **start at §1 and §4.** Everything else is supporting detail.

---

## 0. TL;DR for a reviewer

| Question | Answer |
|---|---|
| Does the engine have a proven edge? | **No.** Best pooled result: +0.47% excess over 20 sessions, t = 1.25. Not distinguishable from zero. |
| Does the score rank stocks? | **Weakly.** Monotone deciles over all names, but among gate-clearers the top bucket is *not* better than the bottom (t = 0.59). |
| Do stop-losses help? | **No — they hurt significantly.** −3.0 to −3.2 pp per 20-session hold, t ≈ −6. |
| Do the gates help? | **Yes, weakly.** They avoid the worst days. This is most of the edge. |
| Is any popular price-action pattern validated here? | **No.** Volatility contraction t = 1.85, sweep/spring t = −0.51, durable-level touch t = +2.08 in the *opposite* direction to the motivating anecdote. |
| What is genuinely worth keeping? | §4 — five things. The other ~45 candidate features are noise. |
| Does the code look correct? | 105 tests pass, all files ≤300 lines, no-lookahead audit enforced. But see §9. |

**The single most important thing to challenge:** the engine bought BAJAJ-AUTO on
2026-09-02, the session after a record-results print, at an all-time high, and lost
17.7%. Every subsequent diagnosis found the *real* cause was a newswire event
(−12% domestic two-wheeler sales, published 2026-10-01) that OHLCV cannot contain.
If you believe price-only screening can address that, §10.1 explains why I doubt it.

---

## 1. What the engine claims

Three separable claims. Conflating them is the most common error in this kind of work.

| # | Claim | Status |
|---|---|---|
| C1 | Some names are **better to hold than others** over 20 sessions | Weak, positive, unproven (t = 1.25) |
| C2 | Some names are **not worth holding at all** (gates) | Supported, small |
| C3 | The score **orders** the names that pass the gates | Not supported |

The engine deliberately does **not** claim to predict next-day returns. Measured:
on 2026-09-29→30, the lowest score bucket returned **+0.13%** vs market and the
highest **−0.01%**. There is no next-day signal. Any claim of one is unsupported.

---

## 2. Data

| File | Contents | Verification |
|---|---|---|
| `data/nse_all_history.parquet` | **2,317 NSE EQ symbols, 1,488 sessions, 2020-10-05 → 2026-10-01** | Priced from yfinance, adjusted |
| `data/universe_history.parquet` | 499 Nifty-500 names, 2,146 sessions, 2018-01-01 → 2026-10-01 | Long-horizon work |
| `data/nse_equity_master.parquet` | 2,317 EQ symbols | — |
| `data/sector_map.csv` | 755 symbols, 22 industries | — |

**Price verification (strongest single fact in this repo).** Prices were cross-checked
against the NSE bhavcopy for 2026-10-01: **100% of 2,311 comparable symbols matched to
within 1 paisa.**

> Reviewer note: the bhavcopy `Series` column has a **leading space** (`' EQ'`).
> Filter without `.str.strip()` and you match nothing, which looks like a data
> failure rather than a string bug.

**Known data limitations, stated plainly:**

1. **yfinance adjusted prices are the only price source.** Bhavcopy is raw. Only
   delivery/trade-count columns are ever merged from it. Mixing the two would
   silently corrupt every return.
2. **No fundamentals, no news, no corporate actions beyond adjustment.** This is
   the binding constraint on the whole project — see §10.1.
3. **Survivorship bias is not corrected.** Symbols present today are used; delisted
   names are absent. This biases results **upward** and I cannot quantify it.
4. **The 52-week component needs 252 sessions**, so the first 252 sessions of any
   panel are warm-up. On the wide panel that is 2020-10-05 → ~2021-11. All pooled
   tests start after it.

---

## 3. How it works

```
yfinance OHLCV
   └─ features.build_features()   per symbol, all windows lagged ≥1 session
        ├─ R5/R10/R20/R60/R252    reference highs (shifted)
        ├─ low10                  10-session swing low (the stop anchor)
        ├─ prox52                 close / R252
        └─ levels.add_levels()    durable_high/low, 260–760 sessions back
   └─ ranking.build_long()        → one row per (date, symbol)
   └─ ranking.rank_all()          → cross-sectional percentiles → score
   └─ quality.gates()             → 7 hard gates → `clears` boolean
   └─ verdict.build()             → forward outcomes for audit
```

**Stop placement** (this was a real bug, fixed): the stop sits below the **10-session
swing low minus 0.25 × ATR**, *not* at the R20 reference. Measured to the reference,
**84.8% of stops were narrower than 1× ATR**, and that bucket had the *worst* forward
returns (+0.23% vs +1.02% for 1–2 ATR stops, 7,953 events). The gate is now a **floor
and ceiling in ATR** (`min_stop_atr: 1.0`, `max_stop_atr: 5.0`).

**Labels are `HISTORICAL_CANDIDATE` / `RESEARCH_CANDIDATE`.** Never "BUY". This is
enforced by convention and by how the site renders.

---

## 4. The five things that survived (everything else is noise)

Everything below is a **per-session** figure — computed within a date, then averaged
across dates. Pooling rows across dates mixes a stock's level with that week's market
regime and manufactures correlation out of nothing. This is the single most common
statistical error in backtesting and it is worth checking that any competing analysis
avoids it.

### 4.1 The gates (C2) — the only solid result

Clears every gate vs does not, 20-session forward return:

| Group | Events | fwd20 | Win rate |
|---|---|---|---|
| Clears every gate | 5,907 | **+0.19%** | 46.2% |
| Does not clear | 931,120 | −0.00% | 43.9% |

Positive but small. The gates are worth roughly **+0.19% per 20 sessions**. That is
the honest ceiling on C2.

### 4.2 The score does order outcomes — over the *whole* universe

937,027 scored observations, 20-session forward return by decile (D1 = lowest):

| D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 |
|---|---|---|---|---|---|---|---|---|---|
| −0.77% | −0.27% | −0.22% | −0.15% | −0.08% | −0.03% | +0.16% | +0.31% | +0.49% | **+0.55%** |

**Monotone across all ten buckets, +1.32 pp bottom-to-top.** This is the strongest
positive result in the repo and it is genuinely good.

### 4.3 …but not *inside* the gates (this is the important negative)

Same decile analysis, restricted to names that cleared every gate, 5,906 events:

| D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 |
|---|---|---|---|---|---|---|---|---|---|
| −0.61% | −0.47% | +0.47% | +0.25% | +0.52% | +0.49% | +0.09% | +1.23% | +0.10% | **−0.17%** |

**Not monotone. D10 vs D1: +0.44 pp, t = 0.59 — no difference.** The ranking orders the
universe but *not* the subset the engine actually buys from. This is the core weakness
and it is why the headline number is small.

### 4.4 Information coefficients (5-day forward, 108,742 breakout events)

| Feature | IC | t | kept? |
|---|---|---|---|
| `atrpct` | −0.0434 | −7.35 | yes |
| `prox52` | +0.0344 | +6.03 | yes |
| `rvol20` | −0.0289 | −5.79 | yes |
| `efficiency` | +0.0178 | +3.73 | yes |
| `penetration` | −0.0174 | −3.57 | yes |
| `ret120` | +0.0147 | — | yes |
| `ret20` | −0.0128 | — | yes |
| `retention` | +0.00009 | +0.02 | **dropped — noise** |

`retention` is included in this table on purpose: it is the repo's "reclaimed-reference
edge", the only hand-built pattern that ever beat the null, and **it is indistinguishable
from zero.**

### 4.5 Two components **flip sign** inside vs outside the gates

| Component | IC inside gates | t | IC outside gates | t |
|---|---|---|---|---|
| `efficiency` | **+0.0321** | +4.15 | **−0.0198** | −18.20 |
| `atrpct` | +0.0357 | +3.77 | +0.0504 | +13.59 |

**Only `efficiency` flips, and it does not matter.** The engine only ever buys
gate-clearers, so the relevant sign is the inside-gate one, and `efficiency` already
carries **+1** — which is the correct sign for that regime. There is nothing to fix.

`atrpct` was previously reported here as flipping too. **It does not**, on the rebuilt
6-year panel, at either horizon: it is positive in *both* regimes (+0.0499 / +0.0532 at
5 sessions, +0.0357 / +0.0504 at 20 sessions). The earlier table was a measurement
error on my part. See error E9.

Also: `penetration` sits at percentile **0.0** for every gate-clearing name — the gate
has already pinned it, so it contributes nothing while still consuming a seventh of the
score.

**I then tried the fix anyway, and it does not work** (`scripts/sign_experiment.py`,
32,389 gate-clearers, 1,187 sessions, 20-session forward return of the top-ranked name):

| Variant | top1 | top3 | top10 | t vs baseline | beat rate |
|---|---|---|---|---|---|
| **A — baseline (unchanged)** | **+1.47%** | +1.69% | +1.59% | — | 49.3% |
| B — flip `atrpct` | +1.34% | +1.74% | +1.87% | −0.22 | 44.6% |
| C — flip both | +1.34% | +1.74% | +1.87% | −0.22 | 44.6% |
| D — flip both, drop `penetration` | +1.52% | +1.91% | +1.90% | −0.15 | 45.0% |

**No variant is significantly different from the baseline**, and flipping `atrpct` makes
the headline number slightly *worse*. The signs are unchanged in the code. A sign is a
fitted parameter; re-measuring justifies changing it, and the measurement does not.

Note the **49.3% beat rate**: the top-ranked name beats the same day's average
gate-clearing name barely half the time.

---

## 5. What did NOT work (measured, not assumed)

### 5.1 Stop-losses are significantly destructive

219 post-warm-up decision bars, top-ranked gate-clearing name, 20-session hold:

| Variant | Mean | vs no stop | t | Win rate |
|---|---|---|---|---|
| **No stop** | **+0.77%** | — | — | 52.1% |
| Flat 7% stop | −2.23% | **−3.00%** | **−5.61** | 27.4% |
| Structural stop (below swing low) | −2.46% | **−3.23%** | **−6.44** | 32.9% |

Both stops are worse than no stop, at t ≈ −6. Names that clear a volatility-aware gate
are volatile by construction; a stop removes them on noise and takes the eventual
winners with it. **This contradicts the widespread belief that a stop is free risk
control.** On this data it is not free — it is expensive.

### 5.2 Named price-action patterns — all three failed

Tested on 499 names, 8 years, 2,146 sessions. Correspondences are noted in prose only;
all column names are price-only (see §7).

| Candidate | Result | t |
|---|---|---|
| Volatility contraction (a VCP analogue): ATR(5)/ATR(40) | IC +0.0035 | **+1.85 — noise** |
| + contraction combined with rising 120d | +0.09% vs same-day | +0.69 — noise |
| A sweep of the 20-session low closing back up | −0.16% vs same-day | **−0.51** |
| Rising 120d AND swept the low | −0.23% vs same-day | −1.51 |

### 5.3 The durable-level hypothesis — the most instructive failure

**The motivating anecdote.** BAJAJ-AUTO made a high of ₹12,285 on 2024-09-27, was
rejected, fell 31.7%, based at ₹9,501 (2025-03-03), then rallied +67% to an all-time
high of ₹12,470 on 2026-09-01 — straight back into the 2024 ceiling. The engine's
longest memory was R252, a rolling one-year high, so the 2024 level was **invisible**.

I built `protocol/levels.py` to fix exactly this. On BAJAJ-AUTO it reproduces the call:
`durable_high = 12285.36` on 2026-09-01, and `level_reject` fires on 2026-09-02 and
2026-09-03.

**Now the pooled test — and the result reverses.**

30,624 gate-clearers with a durable level, 1,121 sessions:

| Group | n | mean fwd20 | vs same-day | t |
|---|---|---|---|---|
| Touched an old level | 19,171 | +1.94% | **+0.18%** | **+2.08** |
| Did **not** touch | 11,453 | +1.47% | **−0.29%** | **−2.14** |

Touching an old level is **mildly positive**, the opposite of the single day that
motivated it. On 2026-09-01 specifically, touchers averaged −6.16% and non-touchers
+8.62% — a 14.8 pp spread that reversed entirely out of sample.

> **This is the single best argument for testing before building.** Had I coded the
> filter on the strength of the anecdote, I would have shipped a rule with the sign
> backwards, backed by a story that felt right.

The U-shaped structure from the earlier measurement does replicate weakly:

| Gap band | n | vs same-day | t |
|---|---|---|---|
| >20% below the level | 5,880 | −0.61% | −2.99 |
| 5–20% below | 4,509 | −0.17% | −0.84 |
| within 5% / at it | 1,956 | +0.53% | +1.92 |
| above (broke out) | 18,279 | +0.13% | +1.41 |

Monotone-ish, but the spread is ~1.1 pp with t-stats of 1–3. **Not strong enough to
be a gate.**

### 5.4 Rotation with real exit rules was negative

Single position, whole account, target-or-stop, redeploy-all, 2021–2026:

- At +15% target / −7% stop with ₹10,000: arithmetic expectancy **+0.48%/trade** but
  **geometric −0.02%/trade**; CAGR negative.
- At ₹1,000 the account ends at **₹205** (−24%/yr). DP charge is 1.59% of capital per
  rotation and 24.8% of time sits idle.
- The top-ranked pick **does not beat a random pick from the same gate-clearers** at
  any grid geometry.
- After the stop-gate fix, rotation got **worse**: rank CAGR −2.3% → −7.5%/yr.

DP cost table: ₹1,000 → 191 bps round trip (17.61% gross needed); ₹10,000 → 57 bps
(15.65%); ₹100,000 → 44 bps (15.50%).

### 5.5 The participation claim failed

Tested the "holding the level beats losing it" claim rather than accepting it:
cohort A (holds reference) fwd20 **+0.61%** vs cohort B (loses it) **+0.77%**. The
claim **failed**, on badly lopsided samples (2,323 vs 250,003 events). Cohort C
(+9.55%) reads the future by construction and is descriptive only.

---

## 6. Live case study — 2026-09-01 → 2026-10-01

The engine's verdict on 2026-09-01. **29 names cleared every gate.** Top 10, ₹10,000
each, entered at the **2026-09-02 open** (you cannot trade the close you used to pick),
valued at the 2026-10-01 close.

| # | Stock | Score | Entry | 1 Oct | P&L | Return |
|---|---|---|---|---|---|---|
| 1 | BAJAJ-AUTO | 0.6761 | 12,211 | 10,045 | −1,774 | −17.74% |
| 2 | WELSPUNLIV | 0.6248 | 199.00 | 239.17 | +2,019 | +20.19% |
| 3 | VARROC | 0.6042 | 865.80 | 830.60 | −407 | −4.07% |
| 4 | BIRLACABLE | 0.6026 | 334.40 | 383.00 | +1,453 | +14.53% |
| 5 | IGPL | 0.5953 | 545.35 | 569.55 | +444 | +4.44% |
| 6 | SAILIFE | 0.5903 | 1,518.10 | 1,541.20 | +152 | +1.52% |
| 7 | CUB | 0.5848 | 231.90 | 230.04 | −80 | −0.80% |
| 8 | SALSTEEL | 0.5776 | 81.99 | 98.92 | +2,065 | +20.65% |
| 9 | MARINE | 0.5638 | 430.28 | 436.55 | +146 | +1.46% |
| 10 | ATHERENERG | 0.5545 | 1,722.00 | 1,406.10 | −1,834 | −18.34% |

**Invested ₹100,000 → ₹102,202. P&L +₹2,202 (+2.20%).** Equal-weight universe over the
same sessions: **−2.70%**. Excess **+4.91%**. 6 of 10 winners.

**Top-1 only (the stated trading style): −17.74%.** Top 3: −0.50%. Top 5: +3.49%.

**With a flat 7% daily stop:** 5 of 10 stopped out, **+₹182 (+0.18%)** — the stop made
the month *worse*.

Context for the BAJAJ-AUTO loss, from the price data: the top-1 pick's 20-session
outcome has mean +0.44%, median 0.00%, sd 6.80% over 480 sessions; it loses more than
7% in 7.3% of sessions and beat the universe in **50.6%** — a coin flip. The −17.74%
sits at the 1st percentile, a genuine tail event, but tail events are what this
distribution is made of.

**The real cause, from the newswire (independently verifiable):**

| Date | Event | Reaction |
|---|---|---|
| 2026-07-21 | Q1 FY27 record: revenue ₹17,244 cr (+37%), PAT ₹3,226 cr (+45.9%), record 1.44m units | **−1.13%** |
| 2026-07-22 | same | **+5.72%** |
| 2026-04-30 | Board considers buyback | +3% "in weak markets" |
| 2026-08-01 | July sales +30% YoY | +2.91% |
| 2026-09-01 | August record 5.35 lakh units, domestic 2W +10% | **all-time high 12,470** |
| 2026-09-02 | **engine buys here** | — |
| 2026-10-01 | September domestic two-wheelers **−12% YoY** (exports +34% masked it in a +32% headline) | **−7.62% to ₹9,900** |

Five catalysts, five reactions. The price never moved on a chart pattern. **The engine
bought at the third consecutive positive announcement, at an all-time high, with no
access to any of it.**

---

## 7. Rules the code is built to enforce

These are not conventions; several are **enforced by tests**.

1. **No source file over 300 lines.** Checked by
   `find protocol scripts tests -name "*.py" -exec wc -l {} +`.
2. **No participant-identity inference.** OHLCV cannot tell you who traded. There is a
   test forbidding claims about accumulation / distribution / supply / demand /
   absorption. Framework names (Wyckoff, ICT, Minervini) appear **only in prose as
   citations**; every column is price-only — `durable_high`, `level_gap`,
   `level_reject`. This was an explicit decision after the user approved a "strict split".
3. **No-lookahead audit** (`protocol/audit.py`) with a `DECLARED_EXEMPTIONS` mechanism
   for legitimate forward shifts. Every exemption is reported with its reason, and
   **stale exemptions are flagged**.
4. **All windows lagged ≥ 1 session.** `_reference_level` shifts by 1;
   `levels.stale_extremes` shifts by 260 *before* rolling. A test rewrites the last 60
   bars and asserts today's level does not move.
5. **Short panels yield NaN, never a guess.** `levels.sufficiency(500)` returns
   `"history is 250 sessions short of the 760 needed"`. Absence must read as absence.
6. **Thresholds live only in `config/protocol_v2.yaml`.**
7. **Labels are `HISTORICAL_CANDIDATE` / `RESEARCH_CANDIDATE`, never "BUY".**
8. **Multiple testing is acknowledged.** `protocol/inference.py` runs Bonferroni and BH
   correction and reports the surviving count.

---

## 8. How to run and how to attack it

```bash
python -m unittest discover -s tests              # 105 tests
python scripts/judge.py --data data/nse_all_history.parquet --asof 2026-09-30 --symbols BAJAJ-AUTO
python scripts/hold_ledger.py --pick 2026-09-01 --mark 2026-10-01 --top 10
python scripts/pick_and_hold.py --from 2025-10-08 --to 2026-09-03 --every 1 --top 1
python scripts/which_to_pick.py                   # top-k vs universe, every session
python scripts/entry_rules.py                     # stop and entry variants
python scripts/rank_diagnosis.py                  # IC inside vs outside the gates
python scripts/pa_signals.py                      # candidate price-action audit
python scripts/rotation_grid.py --capital 10000 --start 2021-01-01
```

**Specific ways to break this engine, in rough order of expected yield:**

1. **Recompute §4.5** and check whether correcting the flipped signs improves the
   top-1 excess. This is the highest-value fix and it is small.
2. **Re-derive §4.3** on a holdout the gates were not fitted on. If the score does not
   order gate-clearers out of sample either, C3 is dead and the engine is a filter, not
   a ranker — and should be relabelled as one.
3. **Find the survivorship-bias magnitude** in §2.3. I could not.
4. **Check the 52-week warm-up boundary.** `pick_and_hold.py` now refuses to run before
   it. An earlier version silently pooled 250 sessions of missing data as if the screen
   were declining to trade.
5. **Verify the ₹ per-rotation DP charge** against a broker's current schedule.

---

## 9. Errors I made, and what they changed

Listed because a reviewer should assume more of these exist than I have listed.

| # | Error | Consequence | Fix |
|---|---|---|---|
| E1 | `verdict.monotonicity()` read `iloc[0]` as "top". Deciles are labelled ascending, so D1 is the **lowest**. | Printed the exact opposite of the truth. | Fixed; direction now labelled explicitly. |
| E2 | While auditing levels, computed `shift(-20)` on the **already-filtered** set, so it spanned the 20th *clearing event*, not 20 sessions. | Produced impossible means of **+89%**. | Recomputed on full history before joining. |
| E3 | Concluded the durable level "should have warned us about BAJAJ-AUTO". | Motivated a filter with the **sign backwards** (§5.3). | Pooled test reversed it. Feature built but **no filter added**. |
| E4 | Predicted the structural stop would save SALSTEEL. | It was stopped on 2026-09-16 at 68.53 by a 1.4% wick, one day before a +32% run. | Reported as wrong; §5.1 shows both stops are worse than none. |
| E5 | `--from` was parsed but never applied in `pick_and_hold.py`. | Date windows silently included all history. | Fixed. |
| E6 | Wrote off the user's Sep-2024 BAJAJ-AUTO read as wrong. | The panel began 3 days after the level was set, so I could not see it. | Fetched 2015+ history; the user was right. |
| E7 | Stated the 1 Oct crash was "a −12% sales print" and framed support/resistance as the cause, then partially reversed myself. | Over-attributed a news event to a chart pattern. | §6 now separates the two explicitly. |
| E8 | Committed a failing audit test. | Caught by CI. | Fixed in the next commit. |
| E9 | Reported `atrpct` as flipping sign inside vs outside the gates. | Would have justified a sign change that **measurably hurts** (top1 +1.47% → +1.34%). | Re-measured on the rebuilt panel: it does not flip. The earlier table was wrong. |
| E10 | In `sign_experiment.py`, selected the top-1 **score value** instead of the top-1 name's **forward return**. | Produced a mean of **+72.55%** and a **99.9%** beat rate. | Caught because the beat rate was absurd. Rewritten to take `nlargest(k, 'score')['fwd'].mean()`. |

**Structural note.** E2, E3, E4, E9 and E10 all share a cause: **reaching for a number
before establishing what it means.** Every one was caught by a sanity check — an
impossible mean, a 99.9% hit rate, a t-statistic pointing the wrong way — and not by
the test suite, which passed throughout. If you find a contradiction in this document,
check my arithmetic first and my reasoning second, and treat any figure I did not
sanity-check as unverified.

---

## 10. What I could not test, and why

**10.1 The news problem is structural, not a missing feature.** The engine has no news
or fundamentals feed. The single largest loss in the live case study was caused by a
−12% YoY print. I can add a news feed; I cannot make OHLCV-based screening robust to
information that is not in OHLCV. Any reviewer claiming otherwise should be asked to
demonstrate it.

**10.2 The usable sample is short.** Post-warm-up the wide panel gives ~1,121 sessions
with a durable level, but only **~248 sessions** of the original 500-session panel were
ever usable. With 499 names that is thin for anything beyond a handful of features.
**Every additional filter multiplies the multiple-testing problem**, which is why §5
rejected three well-known patterns rather than adopting them.

**10.3 No intraday, no order book, no options, no shorting.** Daily bars only.

**10.4 No out-of-sample discipline was applied to the original gates.** The 7 gates
were fitted on this data. There is no clean holdout. **This is the largest structural
weakness in the project** and I do not know how much it inflates the results.

**10.5 One market, one regime.** Indian equities, 2018–2026. No cross-market check.

---

## 11. Honest bottom line

The engine has found **one real effect** — that a small set of names survives a set of
volatility- and trend-aware gates and those names avoid the worst days. It has
**not** found a way to pick the best of them. The ranking that is supposed to do that
does not do it, and two of its components have the wrong sign in the regime it trades
in.

The stop-loss result is the most actionable thing here and it runs against
conventional wisdom: **on this data a stop costs about 3 percentage points per
20-session hold at t ≈ −6.**

Three named price-action frameworks were researched, implemented where implementable,
and **all three failed to clear a t-statistic of 2.** The one idea that survived
measurement — levels older than a year — reversed sign out of sample.

**Recommendation to the owner: do not deploy capital on this engine's output.** A broad
index fund is the better bet on this evidence, because the engine's measured edge
(+0.47% per 20 sessions, t = 1.25) is not reliably distinguishable from zero, and the
single-stock concentration the style requires converts that into a −17% tail event
roughly one time in a hundred.
