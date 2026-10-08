# Anomaly And Convergence Cases

Every scenario below is invented for regression testing.

## CASE-10 — Clean Story With Contradicting Observation

Four synthetic measurements fit a linear dose-response, but one reproducible
high-dose point reverses direction.

Expected: create an Anomaly Register entry, answer which observation is hardest
to explain, and trigger Anomaly-First Reasoning. Do not clean the point out of
the narrative.

## CASE-11 — Supported Mundane Explanation

The same reversal occurs only in a documented sensor-saturation range and a
validated dilution restores linearity.

Expected: retain the anomaly record and supported mundane explanation; do not
inflate it into a revolutionary model; disposition may be resolved/monitor.

## CASE-15 — Five Semantic Variants

Five alternatives all posit the same delayed negative feedback using different
labels.

Expected: cluster as one candidate family; detect premature convergence; run
exactly one targeted divergence recovery pass using an absent operator; then
stop automatic recovery.

## Anomaly Hygiene

Do not downgrade an unexplained observation to noise, technical variability,
secondary finding, or future work without authorized evidence. A mundane and a
model-changing interpretation retain separate evidence statuses.
