"""TrophyDrift: forecast GTA VI trophy earn rates on Exophase a week after launch.

Model
-----
An Exophase earn rate is a ratio, and it moves for two reasons at once:
tracked players keep earning trophies (rates up) while fresh players keep
syncing with almost nothing earned (rates down). The printed rate only
changes when Exophase refreshes its counts, every few hours, so the history
is long flat stretches punctuated by jumps.

What the model does, per trophy, from the case's history:

1. Collapse consecutive reads that change nothing, so flat stretches
   cannot dominate a fit.
2. Fit, by plain least squares, the logit of the rate against
   log(1 + hours since release) over the last 24 hours of distinct reads
   only. A whole-history fit is worse: early launch-night movement is
   steep and extrapolating it overshoots the saturating curves badly,
   while the last day's slope is the shape that actually persists.
3. Shrink the fitted move 25% back toward the last read (0.75 of the
   fitted travel), and damp it further for trophies already above 50%,
   which cannot climb much further: a trophy at 90% has almost no room
   above it.
4. Spread the five quantiles on the logit scale with a random-walk
   width of 0.45 * sqrt(horizon in days) -- a touch narrower than the
   house baseline's 0.5, which the tuning below found slightly
   over-wide -- floored at 0.35 logit units so a short horizon still
   gets a band a refresh can land inside.
5. Enforce the structure the game itself imposes: chapter trophies
   fall in chapter order, the final mission sits below the last
   chapter, the platinum can never sit above any other trophy, and a
   trophy the whole tracked population already holds stays at ~100%.

Tuning: the recipe was chosen on synthetic final cases built two
different ways -- saturating earned-shares with no dilution, and
earned-counts and players saturating on separate clocks so the rate
is their ratio and can fall while players flood in. The shipped
recipe beats both house baselines in both worlds (mean pinball loss
about 0.21-0.28 against about 0.27-0.33 for the house trend baseline and 0.34-0.38
for persistence); the count-model and blend variants that won one
world lost the other badly, so they were dropped.

Quantiles are the median shifted by the normal z-scores on the logit
scale, clamped to [0.01, 99.99] and rounded half-up to 4 decimals.
Everything is deterministic: no randomness, no wall-clock use, fixed
iteration order, so two runs on one case write identical bytes.

Standard library only. Reads $MAKEFUN_INPUT_DIR (else /input), writes
$MAKEFUN_OUTPUT_DIR (else /output), one <id>.out per <id>.in.
"""

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Random-walk spread, logit units per sqrt(day).
RW_SIGMA = 0.45
# Floor on the total logit spread of one trophy.
SIGMA_MIN = 0.35
# Only the last day of reads feeds the slope.
WINDOW_HOURS = 24.0
# Share of the fitted travel the median keeps.
SHRINK = 0.75
# A fitted median needs at least this many distinct reads in the window.
MIN_READS = 3


def clamp_rate(pct):
    """A percent into the range the logit can swallow."""
    return min(99.99, max(0.01, pct))


def logit(pct):
    p = clamp_rate(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(lg):
    return 100.0 / (1.0 + math.exp(-lg))


def round4(x):
    """Round to 4 decimals, half up, returning an int for whole numbers."""
    scaled = x * 10000.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000.0
    return int(value) if value == int(value) else value


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def ols(xs, ys):
    """Least squares for y ~ a + b*x. Returns (a, b) or None."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-12:
        return (my, 0.0)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    return (my - b * mx, b)


def distinct_reads(history):
    """Collapse consecutive reads with identical players and rates."""
    out = []
    prev = None
    for read in history:
        key = (read["players_tracked"], tuple(read["rates"]))
        if key != prev:
            out.append(read)
            prev = key
    return out


def chapter_number(description):
    """Chapter index from a description like 'Complete Chapter 3.', else None."""
    m = re.search(r"[Cc]hapter (\d+)", description or "")
    return int(m.group(1)) if m else None


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    history = case["history"]
    if not history:
        raise ValueError(f"{name} has no history")
    trophies = case["trophies"]

    release = case.get("game", {}).get("release_date") or "2026-11-19"
    try:
        t0 = datetime.fromisoformat(release).replace(tzinfo=timezone.utc)
    except ValueError:
        t0 = parse_time(history[0]["at"])
    target = parse_time(case["target"])
    horizon_days = case["horizon_minutes"] / 1440.0
    x_target = math.log1p(max(0.0, (target - t0).total_seconds() / 3600.0))

    reads = distinct_reads(history)
    last = reads[-1]
    t_cut = parse_time(case["at"])
    window = [
        r
        for r in reads
        if (t_cut - parse_time(r["at"])).total_seconds() <= WINDOW_HOURS * 3600
    ]
    xs = [
        math.log1p(max(0.0, (parse_time(r["at"]) - t0).total_seconds() / 3600.0))
        for r in window
    ]

    sigma = max(SIGMA_MIN, RW_SIGMA * math.sqrt(horizon_days))

    medians = []
    for i, trophy in enumerate(trophies):
        r_last = last["rates"][i]
        if r_last is None:
            r_last = 0.0
        lg_last = logit(r_last)
        lg_med = lg_last
        if len(window) >= MIN_READS:
            ys = []
            ok = True
            for read in window:
                r = read["rates"][i]
                if r is None:
                    ok = False
                    break
                ys.append(logit(r))
            if ok:
                fit = ols(xs, ys)
                if fit is not None:
                    a, b = fit
                    travel = (a + b * x_target) - lg_last
                    # High rates have little room above them: damp the
                    # travel the closer the rate sits to 100%.
                    if lg_last > 0:
                        travel *= 1.0 / (1.0 + math.exp(lg_last))
                    lg_med = lg_last + SHRINK * travel
        medians.append(lg_med)

    medians = enforce_structure(trophies, medians, last)

    rows = []
    for trophy, lg_med in zip(trophies, medians):
        qs = [round4(clamp_rate(inv_logit(lg_med + z * sigma))) for z in Z]
        for k in range(1, len(qs)):
            if qs[k] < qs[k - 1]:
                qs[k] = qs[k - 1]
        rows.append({"id": trophy["id"], "q": qs})
    return {"trophies": rows}


def enforce_structure(trophies, medians, last):
    """Monotone chapter order, platinum at the bottom, ~100% stays ~100%."""
    med = list(medians)

    # Chapter trophies, in chapter order, must not rise with the chapter.
    chain = []
    for i, t in enumerate(trophies):
        c = chapter_number(t.get("description", ""))
        if c is not None:
            chain.append((c, i))
    chain.sort()
    vals = [med[i] for _, i in chain]
    idx = [i for _, i in chain]
    pooled = []
    for v in vals:
        pooled.append([v, 1])
        while len(pooled) >= 2 and pooled[-2][0] < pooled[-1][0]:
            a, na = pooled.pop()
            b, nb = pooled.pop()
            pooled.append([(a * na + b * nb) / (na + nb), na + nb])
    flat = []
    for v, cnt in pooled:
        flat.extend([v] * cnt)
    for k, i in enumerate(idx):
        med[i] = flat[k]

    # The final mission sits after the last chapter: the trophy whose
    # description is exactly "Complete the final mission." -- the
    # substring also appears in side-strand trophies ("...for Andy."),
    # so match the whole description, not a substring.
    final_idx = None
    for i, t in enumerate(trophies):
        if (t.get("description", "") or "").strip() == "Complete the final mission.":
            final_idx = i
            break
    if final_idx is not None and chain:
        med[final_idx] = min(med[final_idx], med[idx[-1]])

    # Platinum: the rarest trophy by construction.
    for i, t in enumerate(trophies):
        if t.get("tier") == "platinum":
            others = [med[k] for k in range(len(trophies)) if k != i]
            if others:
                med[i] = min(med[i], min(others))

    # A trophy the whole tracked population holds stays held.
    for i, t in enumerate(trophies):
        r = last["rates"][i]
        if r is not None and r >= 99.9:
            med[i] = max(med[i], logit(99.0))
    return med


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
