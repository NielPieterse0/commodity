# Commodity: The Big Picture

Commodity is a research platform for answering one practical question: can we find repeatable commodity-market information that survives honest testing strongly enough to support useful trading decisions after costs and risk?

Henry Hub natural gas is the first complete proving ground. It gives us a demanding market in which to build the full data, research, model, decision, risk, and forward-testing process. The platform itself is intended to generalize only after the reference process works.

## Where the work came from

The project began with forecasting and trading ideas, then became progressively stricter as the evidence exposed weaknesses in both models and research plumbing. Early work established data provenance, point-in-time controls, simple baselines, model challengers, fundamental and market-aware signals, and reproducible evaluation. Later audits found places where contract continuity, evidence ownership, freeze discipline, and research interpretation needed stronger controls.

Those lessons changed the project. The repository now treats models as signal producers rather than authorities, separates research evidence from trading permission, and encodes the research methodology so that important claims are checked rather than trusted to memory.

## What we have learned so far

A plausible-looking forecast is not enough. Direction accuracy, model sophistication, or an isolated backtest result matters only when it beats relevant baselines, survives leakage and contract checks, has enough evidence to support the claim, and remains useful after realistic friction and risk.

The first rounds have therefore been valuable even where they did not establish a trading edge: they exposed weak assumptions, improved the data and evaluation system, broadened the signal portfolio, and made the next experiments more trustworthy.

## Where we are going

The durable progression is described in `docs/roadmap.md`: data truth, evidence baselines, complementary signal families, a decision system, forward validation, and only then controlled execution. We are still doing research; live trading remains disabled unless `config/policy.json` explicitly changes that authority.
## How we zoom in

The big picture should stay stable while individual experiments become very specific. Each research question starts by stating how it connects to the programme: what gap it addresses, what earlier observation motivated it, and what decision its result could change.

Exploratory work can investigate that question and generate a sharper hypothesis. When the claim matters enough to confirm, `docs/research-methodology.md` governs the human process and the repository's machine contracts enforce the frozen experiment. The final executive summary then returns the result to this larger view: origin, test, observation, meaning, and programme consequence.

That creates a repeatable loop:

```text
BIG PICTURE -> RESEARCH GAP -> EXPLORATION -> FROZEN EXPERIMENT -> RESULT -> BIG-PICTURE DECISION
```

The purpose of an experiment is therefore not to produce another metric. It is to reduce uncertainty about what the project should believe or do next.
