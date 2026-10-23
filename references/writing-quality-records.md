# Writing Quality Records

Read only when preparing the first lifecycle run or troubleshooting a record.
The per-task `task-packet.json` carries the selected profile; do not load the
engine, both profiles, or a large checklist into ordinary writing context.

## Register Before Drafting

`scripts/writing_lifecycle.py init RUN --plan PLAN.json --profile functional|literary --source SOURCE`
creates a private local run. Repeat `--source` for supplied source files. A
functional run needs captured source or request material. Literary fiction may
have none. Do not store user drafts in the skill package or tests.

The plan contains `task`, `genre`, `domain`, `purpose`, `language`, `format`,
`reader: {knowledge, need}`, `authority: {status, basis, reference}`,
`material: {mode, gaps}`, and `reading_path: [{id, purpose}]`.
`authority.status` is `confirmed` only for requirements grounded in the actual
user request or an applicable confirmed template. The agent may propose
`provisional` requirements and draft, but cannot declare complete acceptance.
Do not turn this into a routine new questionnaire when the request already
provides the required authority.

Functional plans add `required_answers: [{id, question, expected,
source_location}]`. `expected` may explicitly preserve an unknown. Optional
`output_quote` locates the literal answer; it is not a semantic grader.
Literary plans add `literary_intent` and `constraints` (possibly empty).
The unified entry also records `working_title: {text, reason}` before drafting;
`text:null` is reserved for an actual untitled instruction, not an empty default.
They also keep `writing_basis: {given: [text], interpretations: [text],
choices: [text]}` in this same plan, not another checklist. `given` records only
supplied behavior or explicit requirements; provisional explanations belong in
`interpretations`, artistic choices in `choices`. The first two lists may be
empty for free fiction; choices records the current adjustable direction.
Do not make restraint, a moral, or one interpretation a constraint unless the
user actually fixed it. The record preserves a starting point, not a prescribed
reader answer. Later development keeps the original and its version history.
For material-based work, use the existing `choices` list to record consequential
adoption, development, reshaping or omission. A supplied emotional conclusion is
material to judge, not automatically an explicit constraint or an earned story
development. Preserve the user's actual fixed requirements; no per-line inventory.
`material.mode` is `source-grounded`, `fiction`, or `nonfiction`.
`gaps: [{critical, handling, reason}]` uses `unresolved`, `draft-only`, or
`narrowed`; unresolved critical gaps prevent finished acceptance. Changing
requirements or sources requires a new linked task, not overwriting the old
plan to improve a denominator or reset the same unresolved review loop.

## Check A Complete Unit

After a complete argument, section or scene:

```text
python3 scripts/writing_lifecycle.py unit RUN --text UNIT.txt --record UNIT.json
```

`UNIT.json` contains `unit_id`, `summary` and
`observations: [{quote, reason}]`. Use exact text and a substantive reading
observation. A checkpoint is not an independent reader test. Recheck only the
affected unit after a revision; every planned unit must have a current
checkpoint before candidate registration.

## Measure, Then Judge

```text
python3 scripts/writing_lifecycle.py measure RUN --text TEXT --output NEW_REPORT.json
python3 scripts/writing_lifecycle.py candidate RUN --artifact FILE --text TEXT --report NEW_REPORT.json --record ASSESSMENT.json
```

Use the real visible text; HTML/XML extraction skips head, script and style.
Word and PowerPoint text is extracted from their actual package XML; native
formats still need the skill's live readback checks. Unknown delivery types are
rejected instead of skipping content equivalence. PDF needs a separate verified
extraction adapter and is not silently accepted by this engine.
The measurement report is recomputed at registration and cannot be edited into
a pass. It always reports all ten categories, including partial/unmeasured
scope. A missing dictionary, tokenizer, grammar engine or actual page is not 0.

`ASSESSMENT.json` contains:

- `text_sha256`, `report_sha256`: use the `.assessment.json` template emitted
  beside the measurement report. A revised text/report needs a current
  assessment, not an old file with still-matching signal numbers.

- `observations: [{metrics: [IDs], quote, reason}]`: contextual judgment on all
  applicable standards. One observation may cover related standards; do not
  invent ten unrelated issues or repeat a generic checked statement.
- `dispositions: [{signal_id, decision, reason}]`: every actual candidate is
  `retain` with a concrete reason, or `pending`. If repaired, measure the new
  text again. Retained, unchanged expressions do not require repeated repair.
- `not_applicable: {metric: reason}`: only terms with no declared terms, or
  external evidence in authorized fiction without cited factual items. Other
  core standards require a contextual observation, not a blanket waiver.
- `issues: [{blocking, impact}]`: known unresolved problems, not style quotas.
- For rendered outputs, `layout: {status, reason, target, viewport, findings,
  evidence_files}`. `status=unmeasured` permits a candidate, not finished
  acceptance. `inspected` requires actual page evidence. Do not use synthetic
  test pictures as production inspection evidence.

IDs: `vocabulary`, `terms`, `sentence_length`, `paragraphs`, `verbosity`,
`evidence`, `grammar`, `time`, `reading_burden`, `reading_efficiency`.
Counts, contextual judgment, AI replay and real-reader outcomes remain distinct.
There is no quality total, automatic word replacement, literary length limit,
or claim of actual 30-second human comprehension.

Complete-unit checkpoints must cover all delivered visible text without gaps
or overlap. Appending content to a registered whole scene requires a fresh
checkpoint for that scene. Pure layout whitespace does not invalidate a unit.

## Optional Measurement Inputs

- `wordlists: {zh_char: FILE, en_word: FILE}` in the plan: UTF-8 one-entry-per-line
  references; pin the real version. English entries are matched in lowercase.
  Chinese word segmentation is not silently approximated by characters.
- `terms: [{term, definition}]`: explicit definition placement only; contextual
  review still checks ambiguity, meaning and unlisted niche terms.
- `evidence_items: [{source_path, source_quote, output_quote}]`: exact declared
  source-quote binding, not source reliability, causal support or completeness.
- `time_fields: [{label, expected, observed?, kind?}]`, with `kind=date|datetime`
  for ISO parsing; `time_order: [{before, after}]` for declared label relations.
  Relative dates, English tense and narrative time need context; do not infer
  real-world completion from a date match.
- `opening_text`: exact visible prefix, used for literal answer coverage. The
  denominator retains missing answers; placement is not successful reading.

For five physical layout measures pass `measure ... --geometry GEOMETRY.json`.
Capture actual target-page lines through the authorized browser/native tool;
record `text_sha256`, `target`, `capture_method`, `state` (`default` or
`expanded`), `viewport_height`, `content_height`, `unmeasured_content`, and
`lines: [{id, block_id, text, y, height, font_size, line_height, paragraph_gap?}]`.
Coordinates are relative to the measured content start. Unique line IDs avoid
double counts. Measure default/expanded states separately. The engine computes
screen characters, longest block lines, total screens, line characters and
spacing ratios. It cannot authenticate coordinate capture or measure fatigue.

## Independent Review And Final Delivery

Call `review-start RUN --artifact FILE --stage during|after` before starting the
independent calls. Early reviews and final reviews share the same three-round
budget; one parallel batch is one round. Record all returns before revising.
`review-finish RUN --result ORIGINAL_RESULT.json --verdict pass|fail` binds the
original result. A failure needs specific unresolved reader impact.

Functional skills reuse their existing role packets and final verifier; they
do not add another review panel. The lifecycle result must be the exact native
aggregate or scoped receipt revalidated by the existing final delivery code.

Literary `review-start` creates two isolated packets. Give fresh professional
and reader sessions only their respective packet. Do not fork author context
or give the reader author intention, expected answers or prior feedback.
Original results contain `reviewer_records` for `professional` and `reader`,
each with `context_id`, `packet_sha256`, `verdict`, `summary`, and
`evidence: [{quote, reason}]`; the result also carries `issues`. Both must pass.
The reader additionally returns the packet's `reading_response`:

```json
{
  "understanding": {"observation": "What this reader understood, including uncertainty", "quote": "Exact current text"},
  "experience": {"observation": "Where attention, interest or distance arose; no praise required", "quote": "Exact current text", "disposition": "no-change", "finding_ids": []}
}
```

The professional additionally returns `development_response` in the same result,
with `observation`, `quote`, `disposition`, `finding_ids` and `checks`.
Use the actual packet's generated template, not a manually shortened example:
every ID in [review coverage](review-coverage.md)
is required, with `before_quote`, `after_quote`, `observation`, `disposition`,
`finding_ids` and `comparison: {needed, reason, trial}`. If comparison is needed
and the reviewer supports retaining the passage, `trial` contains actual
`current`, `alternative`, `gain`, `loss`, `attention_cost`; a paragraph-only
trial adds `kind:paragraphing`. Otherwise explicitly return null and explain why.
Unperformed comparisons remain linked editorial/blocking work, not a pass.
`revision_effects` also returns `baseline_evidence: [{id, sha256, quote, reason}]`
from the supplied designated source and previous candidate when present. An
original work without either uses an empty list, never an invented earlier draft.

Use `supported`, `blocker`, `editorial`, or `not-applicable`. A blocker references
nonempty stable IDs in this return's `issues` and requires a failing verdict;
editorial references its actual `editorial` IDs. Supported/not-applicable leave
IDs empty. Static or non-narrative work may use not-applicable with an actual
passage and a reason, not an invented conflict. Language, paragraph rhythm and
opening/ending still need review for static or untitled work. Quote the necessary context in
the observation/evidence; quoting a reaction alone does not establish support.
Material wording is not proof of story development. The reader receives none
of this source-aware response, nor a prescribed explanation of the story.
Missing answers, stale quotes and broken finding links are record failures;
semantic plausibility remains a professional judgment, not a program verdict.
Both checks are required in the same response. Quotes must belong to the current
body; blockers/editorial choices must link to actual findings just like the
parent response. A supported parent cannot hide a failing subcheck. Static or
non-narrative work may explain not-applicable without inventing a plot; no quota
of explicit transitions or actions is imposed. After repairs, reread affected
premises, locations, knowledge, actions, object states and responses before
requesting the next review. Do not reuse prior quotes or judgments for a new draft.

Experience disposition is `no-change`, `editorial` or `suggestion`; the latter
two reference nonempty IDs in this same return's `editorial` or `suggestions`.
Missing answers or stale quotes are incomplete review records, not literary
failure. A reader may understand the text without caring about its characters;
report that separately. Consequential unresolved artistic choices use editorial
findings, minor improvements use suggestions; neither requires a prescribed
feeling or an automatically failing verdict. Do not repeat the author intention
as the reader's experience or pass it into the reader packet.
Role names and hashes are traceable records, not authenticated independence.
The existing clean/comparison readings remain author self-checks, not these
independent calls. Do not require readers to identify one prescribed theme.

Use the skill's checked delivery with `--lifecycle-run RUN`. A bare low-level
semantic/record validator is not whole-workflow acceptance. After three failed
rounds, use the skill's draft-only exit: return the current version, unresolved
impact and a user choice. It cannot authorize publishing or a fourth retry.

Three-round exhaustion depends on the current version still failing after
three completed batches; a previous version's pass does not hide a regression
or prevent the current draft from being shown.

These scripts reject skipped registered stages and stale evidence when called.
They do not install a host hook, prove the actual generation chronology, make
records tamper-proof, or prove human understanding or literary quality.
