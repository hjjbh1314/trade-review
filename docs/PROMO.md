# Promo kit

Copy-paste social posts for Trade Review. Angle: **honesty** — this repo ships
the backtest that proves its own factors wrong, not the one cherry-picked to
look good. That's what earns trust (and stars) with the quant/dev crowd.

Repo: https://github.com/hjjbh1314/trade-review

> Before posting: the quant module and these charts must actually be on GitHub.
> Commit & push first, or the link shows a repo without the thing the post is about.

---

## X / Twitter

### Single tweet (attach `screenshots/backtest_factor_ic.png`)

> I open-sourced my AI trading journal — and the quant backtest that ships with
> it told me my favorite factors are garbage.
>
> Momentum on the A-share mainboard? **Negative** Rank-IC. So the code deleted it.
>
> Self-hosted, MIT, runs on Claude or DeepSeek 👇
> github.com/hjjbh1314/trade-review

### Thread (6 tweets)

**1/** _(the single tweet above, + `screenshots/backtest_factor_ic.png`)_

**2/** What it is: a personal AI trading *coach*. Flash-review every trade in
≤10s, daily portfolio review, a weekly "mindset radar" of your behavioral
patterns — plus a multi-factor A-share screener. Runs on your laptop. Claude
Code OAuth (no API key) or DeepSeek.

**3/** The quant part is honest. 4 factors survived 3 years of backtest —
short-term reversal, low-vol, value, small-cap. Composite Rank-IC +0.08→0.10,
ICIR ~0.6, and it survives walk-forward (out-of-sample IC +0.048).
_(+ `screenshots/backtest_equity.png`)_

**4/** But here's what most "quant" repos hide: positive IC ≠ a tradable edge.
The long-only Top-20 does **not** robustly beat a dumb equal-weight basket — in
the 2025 rally the basket won outright. I shipped that chart anyway.

**5/** Write your own strategy = drop one file. Pick validated factors, weight
them, backtest in one command:
`python -m backend.quant.backtest --strategy my_reversal`
Momentum & chase-volume aren't even available — the backtest showed they hurt.

**6/** MIT. Not investment advice — it's a journaling/coaching tool and the AI
can be wrong about prices & fundamentals. If "a quant repo that won't let me lie
to myself" sounds useful, a ⭐ helps:
github.com/hjjbh1314/trade-review

### Posting notes

- **Images**: `screenshots/backtest_factor_ic.png` (red/green factor IC — lead
  image) and `screenshots/backtest_equity.png` (equity curve — tweet 3).
- **Hashtags**: keep to 2–3, e.g. `#quant #Python #opensource`.
- **Link reach**: X tends to suppress posts with outbound links. For max reach,
  put the repo link in the *first reply* instead of the main tweet.

---

## Chinese version (雪球 / V2EX / 即刻)

> 我把自己的 AI 交易复盘工具开源了 —— 顺便把那个**打我自己脸的回测**也一起放上去了。
>
> 动量因子在 A 股主板？回测出来是**负 Rank-IC**,代码直接把它删了。
>
> 自托管,MIT,Claude 或 DeepSeek 都能跑。3 年数据、可插拔策略、写自己的因子组合一条命令回测。
> 正 IC ≠ 能交易的组合 —— 长多组合跑不赢等权基准这事我也照实画进图里,没藏。
>
> github.com/hjjbh1314/trade-review

---

## One-liners (HN "Show HN", README tagline, etc.)

- Show HN: An AI trading journal whose quant backtest deletes its own bad factors
- A self-hosted AI trading coach + multi-factor screener that's honest about what
  doesn't work
