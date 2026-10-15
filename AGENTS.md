# Webdebit — agent guide for this repository

This repository is a sanitized code-and-fixture subset of HTH accounts receivable work. It is NOT a production ledger or a full copy of `D:\webdebit`. Never reconstruct real transactions from fixtures or use repo code to post against production.

- `cong-no-web-handoff/pilot/`: read-only reconciliation engine. `web/`: two read-only web views. `tools/`: schema/import/verification code only; deployment, SSH relay, live submission and source-capture scripts are deliberately excluded. `tests/` and `preview/` use synthetic fixtures.
- From `cong-no-web-handoff/` on Windows run `py -3.13 -m unittest discover -s tests -v`, `node preview/test-so-cong-no-model.js`, `node preview/test-monthly-ledger-model.js`. Run the relevant other `preview/test-*.js` for UI changes. No live DB is needed for these tests.
- Money is exact integral VND; NULL is not zero. Preserve customer and debt period, separate event date from posting date, keep pending outside balances. Do not merge trips by container. No financial post without source, evidence and separate approval. Never rewrite a posted transaction: reversal/adjustment requires audit.
- Business context in this public-safe subset is intentionally incomplete. Source snapshot, production opening, actor rights, detailed decisions, design probes and customer-level evidence remain local. Ask for reviewed requirements before changing financial behavior; classify proposal, approved policy, implementation and verification separately.
- Do not add raw captures, exports, dumps, bank documents, customer screenshots, exact spreadsheet IDs, SSH details, internal host paths, credentials, or unreviewed generated artifacts. Run a staged-file review and secret scan before pushing.
