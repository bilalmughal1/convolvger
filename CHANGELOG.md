# Changelog

All notable changes to Convolvger will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-09-16

### Added

- A finding records `occurrences`, the number of times the same observation was
  made. One decoder can meet the same unmodelled shape dozens of times in a
  single snapshot; collapsing those into one finding with a count keeps the
  report readable without losing how much of it there was
- Claude conversations can be archived. A Claude share page cannot be fetched:
  its conversation loads separately and the service refuses non-browser clients
  whatever headers they send. Rather than impersonate a browser, `--capture` on
  `export` and `inspect` waits for yours, and the new `convolvger bookmarklet`
  command prints the bookmarklet that hands a snapshot over. The listener is on
  loopback, takes one snapshot, and accepts it only when the browser's origin
  matches the address the payload claims. Nothing is impersonated and nothing
  leaves the machine
- Tool calls and tool results are first-class content. A conversation that used
  tools now records each call with its arguments, and whatever result the
  snapshot carried, nested as canonical blocks. The Markdown export states
  plainly when a result was not carried at all, instead of rendering nothing.
  Both previously landed as unrecognised blocks, which made every tool-using
  conversation report a fidelity loss it had not actually suffered

### Changed

- A conversation carries `provider_metadata`, for envelope fields this version
  does not model canonically. Claude's snapshot names the account that shared it
  and says whether the snapshot still matches the conversation it came from; the
  JSON archive keeps all of it and no renderer reads it. Schema 3 was not
  released, so no reader exists that this could break
- Archive schema version 3. An archive written by version 2 still loads: a
  version stays readable for as long as this tool can represent it truthfully,
  and a test reads a real archive produced by 0.1.1 to prove it. Version 1
  remains refused, because its list of warning strings has no honest reading
  here and accepting it reported a clean verdict on a damaged file

## [0.1.1] - 2026-09-12

### Added

- `--from-file` on `inspect` and `export`: parse a saved copy of a share page
  instead of fetching the URL, so a capture can be re-read without asking the
  provider for it again. The URL is still required, since it routes the snapshot
  and records its provenance; no retrieval time is claimed for a saved file

### Fixed

- A deferred turbo-stream slot is now reported as a fidelity loss rather than an
  incomplete snapshot. The stream carries the deferred line and this decoder
  discards it, so the earlier verdict blamed the provider for the decoder's own
  gap
- Install and usage instructions in the README, which were mangled when the
  0.1.0 release metadata was written and so shipped broken to PyPI

## [0.1.0] - 2026-09-12

### Added

- Initial project structure
- Provider-independent CLI foundation
- Initial project documentation
- MIT license
- Canonical conversation model with typed content blocks, preserving
  unrecognised content verbatim rather than dropping it
- ChatGPT provider: share URL detection, snapshot retrieval, turbo-stream
  decoding, and mapping onto the canonical model
- Markdown export with a provenance header reporting every omission
- JSON export (`-f json`): the complete archival record, omitting nothing
  the canonical model holds
- Structured findings with stable codes and note/warning levels, replacing
  free-text extraction warnings
- Integrity aspects: every finding code is mapped to the question it answers
  -- snapshot completeness, modelling fidelity, or neither -- in one total
  table, kept in step with the severity table by a test
- Archive reader that refuses any file whose declared schema version this
  version cannot read, rather than validating it into a false clean verdict
- `convolvger verify PATH`: reports an archive's integrity from the findings
  it already carries, re-fetching and re-parsing nothing
- Continuous integration running the full quality gate on every push and
  pull request
- Packaging metadata for publication: a licence expression, classifiers,
  project URLs, and a `py.typed` marker so type checkers use the annotations
  the package already ships

### Changed

- Archive schema version 2: the envelope's `warnings` list of strings is
  replaced by `findings`. Renaming a field is a breaking change; adding one
  is not
- Archive envelope now preserves fields written by a later version instead
  of rejecting or silently discarding them
- Exit code 2 is now raised only by warning-level findings. Empty messages
  a public snapshot omits by design are recorded as notes and leave the
  exit code at 0
- Quality gate covers tests as well as sources (`mypy src tests`), and is now
  strict rather than nominal: `mypy` runs in strict mode, and `ruff` selects
  import-order, pyupgrade, bugbear, simplify and ruff-specific rules on top of
  its defaults
- A literal object key in a provider payload is recorded as an observation
  rather than a fidelity loss: the decoder returns such a key verbatim, so
  nothing is lost on that branch

### Fixed

- Non-standard JSON constants (`NaN`, `Infinity`) in a provider payload are
  reported instead of becoming `null` unannounced
- A message weight the snapshot never carried no longer warns as an
  unexpected value. An omitted field and an explicit null are different
  things, and the absence is recorded as a note so that a provider dropping
  a field it always sent stays visible
