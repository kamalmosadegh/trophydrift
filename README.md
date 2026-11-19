# TrophyDrift — GTA VI trophy rarity forecast

Forecasts, for every PlayStation 5 trophy of Grand Theft Auto VI, the
percent of players Exophase tracks who will hold it at 2026-11-26T00:00:00Z,
as five quantiles (5/25/50/75/95%) per trophy. Scored by mean pinball loss
on the logit scale.

## The program

`main.py` (Python 3.13, standard library only) reads every `*.in` case in
`$MAKEFUN_INPUT_DIR` (else `/input`) and writes one `<id>.out` per case to
`$MAKEFUN_OUTPUT_DIR` (else `/output`):

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## The model

An Exophase earn rate is a ratio — trophies earned over players tracked —
and it moves both ways: tracked players keep earning (rates up) while
fresh players keep syncing with almost nothing earned (rates down). The
printed rate only changes when Exophase refreshes its counts, every few
hours, so the history is flat stretches punctuated by jumps.

Per trophy:

1. **Dedupe** consecutive reads that change nothing.
2. **Last-24-hours trend**: least squares of the logit's rate against
   `log(1 + hours since release)` over the last 24 hours of distinct
   reads only. A whole-history fit is worse — early launch-night
   movement is steep and extrapolating it overshoots the saturating
   curves, while the last day's slope is the shape that persists.
3. **Shrinkage**: the median keeps 75% of the fitted travel from the
   last read, damped further above 50% (a trophy at 90% has almost no
   room above it).
4. **Spread**: quantiles sit at normal z-scores on the logit scale with
   width `0.45 * sqrt(horizon in days)`, floored at 0.35 logit units.
5. **Game structure**: chapter trophies fall in chapter order (pool
   adjacent violators), the final mission sits below the last chapter,
   the platinum is never above any other trophy, and a trophy the whole
   tracked population holds stays at ~100%.

Deterministic: no randomness, no clock use, fixed iteration order — two
runs on one case write identical bytes. Runs in ~0.05 s on the practice
cases, far inside the 8 s cap.

## Tuning

The recipe was chosen on synthetic final cases built two different ways:
saturating earned-shares with no dilution, and earned-counts and players
saturating on separate clocks so the rate is their ratio and can fall
while players flood in. The shipped recipe beats both house baselines in
both worlds (mean pinball loss ~0.21–0.28 vs ~0.27–0.33 for the house
trend baseline and ~0.34–0.38 for persistence). Count-model and blend
variants that won one world lost the other badly, so they were dropped.
