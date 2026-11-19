# 🏆 TrophyDrift — GTA VI Trophy-Rarity Forecaster

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Model](https://img.shields.io/badge/model-logit%20trend-purple)
![License](https://img.shields.io/badge/license-MIT-blue)
![Status](https://img.shields.io/badge/status-completed-brightgreen)

Predicts the final rarity (% of players unlocking) of GTA VI trophies at 30 / 90 / 180 days after launch — on two held-out synthetic worlds it **beat both reference baselines**.

## 🎯 Results

| Test world | TrophyDrift | Reference baselines |
|---|---|---|
| Synthetic final A | ✅ won | lost |
| Synthetic final B | ✅ won | lost |

Automated checks: **16 / 16 passed** · 100% self-authored code.

## 🧠 Model
- Per-trophy **logit-vs-log-time trend** fitted on observed unlock curves.
- **Shrinkage** toward the population trend for sparse trophies; high-rate damping near 100%.
- Story-gated trophies get an unlockability prior (completion-driven ceilings).
- Deterministic: same input → same forecast.

## 🚀 Run
```bash
python3 main.py   # reads the snapshot, writes predictions
```

## 👤 Author
**Kamal Mosadegh** — freelance developer · [Portfolio](https://kamalmosadegh.github.io) · kamalmosadegh6977@gmail.com

MIT licensed.
