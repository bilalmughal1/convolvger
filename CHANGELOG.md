# Changelog

All notable changes to Convolvger will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

### Changed

- Archive schema version 2: the envelope's `warnings` list of strings is
  replaced by `findings`. Renaming a field is a breaking change; adding one
  is not
- Archive envelope now preserves fields written by a later version instead
  of rejecting or silently discarding them
- Exit code 2 is now raised only by warning-level findings. Empty messages
  a public snapshot omits by design are recorded as notes and leave the
  exit code at 0
- Quality gate covers tests as well as sources (`mypy src tests`)
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
