# Annotation workflow moved to IntelliAudit

The canonical dataset-authoring and accountant-review protocol is maintained
in [IntelliAudit](https://github.com/manmad-web/IntelliAudit/tree/codex/accountant-review-dashboard):

- `docs/ANNOTATION_PROTOCOL.md` — one-accountant review, uncertainty, authority,
  proof alternatives, delayed blind repeats, grouped splits and claim limits.
- `docs/RELEASE_GATES.md` — team responsibilities and the distinction between
  working dashboard reviews and publication annotation records.
- `review/annotation.schema.json` and its blank/unreviewed examples.
- `scripts/validate_annotations.py` and `scripts/check_release_readiness.py`.

Run those tools in an IntelliAudit checkout. There is deliberately no second
schema or validator in this pipeline repository. Model experiments consume
versioned reviewed datasets; they do not manufacture or approve their own gold.

One qualified accountant is available. Until actual review is completed, the
pilot remains unreviewed development material. A future completed release may
claim single-expert review and delayed intra-rater stability, not two-expert
adjudication or independent gold-standard validation. No completed human review
or new model result is asserted by this move.
