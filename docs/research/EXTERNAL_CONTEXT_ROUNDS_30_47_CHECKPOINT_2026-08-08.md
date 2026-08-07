# External-context account research checkpoint: rounds 30–47

## Current decision

V3 remains unchanged. No external-context overlay is approved for paper tracking or runtime publication.

The strongest research challenger is the round-46 tiered, event-conflict-gated, 40-trading-day winner extension. It passed the tuning and validation gates and produced a 15.99% relative total-return improvement in the reused final readout, with the frozen V3 buy-symbol set and identical skip rates. It did not clear the exact final non-degradation gate because maximum drawdown was 6.946% versus 6.885% and the worst partial-month return was 0.44741% versus 0.44792%.

Round 47 froze both V3 buy symbols and share counts. It retained a 12.48% relative final return improvement, but a 0.0106 percentage-point validation return deficit prevented pre-final selection. This confirms that the return advantage is not solely caused by larger downstream V3 entries, but it also shows that the available pre-final trigger sample is too small for a production claim.

## What was learned

- Early-exit overlays did not survive the final readout.
- A global/sector residual is more useful as a holding-period modifier than as a buy trigger.
- Fixed cash reserves protect buy capacity but discard most continuation payoff.
- Exact entry-day liquidity recall preserves V3 buys but sells the intended winner too early.
- Cash-fit sizing and weakest-core-position substitution improve the return/liquidity trade-off.
- Tight 5%/8% trailing protection exits genuine continuation winners too early; tiered protection is materially better.
- Recent official company events behave better as a conflict/risk gate than as a positive buy signal in this sample.
- The standout result is concentrated in very few positions, especially `603115.SH`; it is not yet robust enough to call verified alpha.

## Validation correction

The segment metric implementation previously reused whole-calendar-month returns when a segment began mid-month, causing validation and final monthly metrics to overlap. Segment monthly returns are now recomputed from each segment's starting NAV, and order metrics use trade day rather than signal day. A boundary regression test was added.

## Integrity checks

- Offline replay only; no network access during historical evaluation.
- `available_at <= decision_cutoff`; no future feature or label violations reported.
- Lambda-zero reproduces the frozen V3 NAV and executed buy/sell ledger.
- External information never creates an independent positive buy trigger.
- Targeted research/replay tests: 42 passed.
- Full repository regression: 1,289 passed, 181 deselected, 6 subtests passed.
- Ruff on changed research/replay files: passed.
- Policy audit: passed.

## Next required proof

Do not tune further on the reused final period. The challenger now needs a trigger-concentration audit, leave-one-trigger-out/decomposition, prior-close sizing and adverse execution stress, and a new untouched forward paper window. If the result depends on one position or fails realistic execution, retain V3 at external weight zero.
