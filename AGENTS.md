# NiriKsha Agent Context

## 1. What this project is
NiriKsha is an AI-Assisted Legal Metrology Packaged-Commodity Inspection System for SIH 2026 PS 26034, built as a government compliance-checking tool for Department of Consumer Affairs field inspectors. It is an evidentiary and enforcement tool, not a consumer app: false positives that wrongly flag a compliant product and false negatives that miss a real violation both carry real legal weight.

## 2. Read these files before making any change

- [docs/architecture.md](docs/architecture.md) — Read for the system architecture and data flow.
- [docs/api.md](docs/api.md) — Read for the full REST API reference, including Supervisor Management and Known Limitations sections.
- [docs/deployment.md](docs/deployment.md) — Read for Render/Neon deployment requirements, including the `--workers 1` constraint.
- [docs/security.md](docs/security.md) — Read for authentication, RBAC, sensitive-data protections, and the AI-agent behavioral rules specific to security changes.
- [backend/rule_engine/registry.py](backend/rule_engine/registry.py) — Read for the 12 pinned statutory rule definitions. Never modify a rule's statutory citation without verifying it against the actual Legal Metrology (Packaged Commodities) Rules, 2011 PDF text, not memory or a summary.
- [backend/models.py](backend/models.py) — Read for the 17 SQLAlchemy tables/models and their relationships before changing persisted data or cascades.

## 3. Non-negotiable technical invariants

- PostgreSQL on Neon is the only supported database. SQLite is rejected by both configuration and engine guards. Never write code, tests, or documentation implying SQLite is supported, even as a quick local option.
- OCR and inspection creation use process-local synchronization. `backend/main.py` currently defines `_creation_lock` as a `threading.Lock`; `OCR_CONCURRENT_IMAGES` is configured as `1`. The deployment documentation also refers to an `_ocr_concurrency_guard`, but that symbol is not currently present in `backend/main.py`. These safeguards are not distributed locks and only provide their guarantee within one worker process. Run with `--workers 1`; replacing them with a distributed lock such as a PostgreSQL advisory lock is required before recommending multiple workers.
- OCR and extraction must never fabricate text. If confidence is low or text is genuinely absent, use `NOT_FOUND`, `LOW_CONFIDENCE`, or `INSUFFICIENT_EVIDENCE` as appropriate. Never invent a value and never derive `POTENTIAL_NON_COMPLIANCE` from uncertainty alone.
- The rule engine in [backend/rule_engine/engine.py](backend/rule_engine/engine.py) and the declaration validator in [backend/declaration_validation_service.py](backend/declaration_validation_service.py) are the single sources of truth for their respective statutory validation. Do not reintroduce parallel validation logic for the same statutory field; duplicate validators have previously produced contradictory compliance verdicts.
- Evidence is immutable after an inspection is `COMPLETED` or has a generated report. Inspectors cannot edit images, declarations, or findings after that point. Only supervisor/admin deletion, with a full audit trail, may remove the relevant entities.
- Verify statutory rule citations, rule numbers, sub-clauses, and thresholds against the actual Legal Metrology (Packaged Commodities) Rules, 2011 text before writing them into code, comments, or documentation. Do not trust an existing citation merely because it is already in the repository. Known corrections include the font-size table being Rule 7(2), not Rule 9, and the misleading-terms check being Rule 12(6), not Rule 13(5).
- Any change to `PADDLE_OCR_VERSION`, `PADDLE_OCR_LANG`, `OCR_ENGINE`, or any other setting that directly controls which OCR model or engine is used **must be explicitly called out in its own commit message** as an accuracy-affecting change, and **must be flagged to the developer for sign-off** before merging. Silent downgrades to lower-accuracy models to save memory or simplify deployment are treated as the same category of defect as a silent statutory citation error: both can cause the system to miss a real violation or wrongly flag a compliant product. The current required model is `PP-OCRv6_medium` (83.2% recognition accuracy, arXiv:2606.13108). Any deviation from this must document the accuracy trade-off explicitly.

## 4. Behavioral rules for AI agents working on this codebase

- I never make a failing test pass by reverting or weakening the underlying fix that caused it to fail. If a test expectation looks wrong, I prove it with the specific source of truth, such as the actual law text or API contract, instead of merely making the red go away.
- I never report a diff as applied without showing actual `git diff --stat` or `git status` output proving that it landed on disk. A diff in a chat message is not the same as a diff written to a file.
- I never use a test filter such as `-k`, `--deselect`, or named-test selection without stating which tests were excluded and why in the same message as the results.
- I never invent or paraphrase a code diff from memory. When asked to show a diff, I run the actual diff command and show its real output.
- When citing a package version, platform pricing/resource tier, or other external fact that may change, I verify it against a current authoritative source instead of repeating a remembered figure. Incorrect Render resource assumptions and incorrect rule citations have both caused rework here.
- When two files independently validate the same business rule and disagree, I treat the disagreement itself as the bug, even if both files appear to work independently.

## 5. Where to get more context

For column-level and endpoint-level detail beyond the summaries in `docs/architecture.md` and `docs/api.md`, read [NIRIKSHA_DATABASE_REFERENCE.md](NIRIKSHA_DATABASE_REFERENCE.md) and [NIRIKSHA_API_REFERENCE.md](NIRIKSHA_API_REFERENCE.md).
