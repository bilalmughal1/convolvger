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

### Fixed

- Non-standard JSON constants (`NaN`, `Infinity`) in a provider payload are
  reported instead of becoming `null` unannounced
