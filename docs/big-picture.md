<!-- GENERATED FILE. DO NOT EDIT. Source: AGENTS.md -->

# Commodity

`Commodity` is an experimental commodity-market research platform. Reusable platform logic MUST remain instrument-independent; any market-, instrument-, venue-, contract-, data-source-, or execution-specific difference MUST be owned by a bounded adapter, configuration, programme, or research slice rather than by the repository purpose.

## Primary objective

Build a reproducible system that can:

1. screen tradable instruments and market states for economically plausible opportunities before committing deep research effort;
2. ingest and version market, fundamental, cross-market, and explanatory data with point-in-time controls;
3. produce complementary signal families from forecasting, regime/trend, technical, fundamental/event, volatility, and cross-market methods;
4. validate, calibrate, and combine signals without leakage, using appropriate baselines and governed model or ensemble selection;
5. translate validated evidence into bounded trade candidates, position/risk decisions, and realistic execution assumptions;
6. forward-test the complete decision process in simulation or paper execution; and
7. determine whether the integrated system remains robust after realistic costs, regime changes, uncertainty, and risk controls.
