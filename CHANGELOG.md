# Changelog

All notable changes to Convolvger will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Grok conversations can be archived from a share link. The page is an
  application shell that loads its conversation as JSON, so Convolvger asks
  that endpoint directly: no browser, no cookie, no token, and this tool's own
  User-Agent. The share id is kept whole whatever its prefix, since what the
  prefix means is Grok's business and a new one should not make a working link
  look foreign
- A Grok answer carries its citations as inline markup that would otherwise
  land in the Markdown as raw tags. Each one whose card the payload carries is
  lifted out of the visible text, and the message exactly as served is kept
  beside it in the JSON, so nothing the provider sent is lost. Markup of any
  other shape is left in the text and flagged, because text this version
  cannot account for should be shown rather than hidden
- Search results, X posts, citation cards, model names and response ids are
  kept in the JSON archive under `provider_metadata`, and none reaches
  Markdown. The payload is keyed, so every field is kept by construction rather
  than enumerated by hand. That includes the sender exactly as served: it
  arrived as `human`, `ASSISTANT` and `assistant` within one conversation, and
  folding it into a role should not erase which casing the provider sent
- The reasoning trace Grok shows beside a thinking answer is kept whole but
  reported as unmodelled content, since its shape has been seen in only one
  conversation. Files and images a response names but does not carry are
  reported as withheld, and nothing is fetched to fill the gap
- A missing Grok share is reported as one, whether the provider says so with a
  404, rejects a malformed id with a 400, or answers 200 with a title and no
  messages. That last case was seen on a real public share, and exporting it
  would have passed an empty conversation off as a real one
- A weekly contract check for Grok, against a share made for the purpose, in
  its own job so a failure names the provider that changed

### Fixed

- A busy capture port is reported on Windows. The listener allowed address
  reuse, which on Linux only skips the wait after a previous run, but on
  Windows lets a second socket bind a port another program is listening on.
  The collision went unreported there, and the test that says so failed on
  native Windows. The test suite now runs on Windows in CI as well as Linux

## [0.4.0] - 2026-09-21

### Added

- Gemini conversations can be archived from a share link. The share page turned
  out to carry no conversation at all: it is an application shell whose only
  prose is Google's own marketing examples, so a text scrape of it returns a
  plausible archive of the wrong conversation. Convolvger asks the endpoint the
  page itself asks, and sends only the one query parameter that proved
  necessary. The build identifier a browser sends is deliberately not pinned,
  since it names a Google build and would rot on their schedule. No cookie is
  sent and no token is needed: the request succeeds with this tool's own
  User-Agent, so nothing impersonates a browser
- All three link forms Google issues are accepted. Two carry the conversation
  id in the path and cost nothing extra; the third is a shortener whose token
  is not the id, and it is resolved from its redirect rather than by
  downloading the page behind it
- A Gemini answer arrives as flat Markdown, and the payload also carries a
  block tree that re-decomposes the same text for the web UI. Every heading,
  bullet and table cell of a real conversation was found present in the flat
  string, so the tree is passed over: nothing is lost by ignoring a second copy
  of content already kept in full. Citations and the searches the model ran are
  a different matter, appearing nowhere in that text, and are preserved in the
  JSON archive. No renderer reads them, so the document a reader sees stays
  clean while the archive stays complete
- A missing Gemini share answers with a success status and a null payload
  rather than an error, so the status code alone cannot tell a deleted
  conversation from a present one. Convolvger reports it as a missing share
  instead of passing an empty conversation off as a real one
- `convolvger --version` reports the installed version, the interpreter, the
  archive schema it writes and the ones it can read, and the providers the
  build supports. Every archive already recorded the version that wrote it
  while nothing let a user ask which version they were running. Nothing is
  fetched to answer: a tool that keeps conversations on your machine has no
  business contacting an index to describe itself, and a test fails the build
  if it tries

### Changed

- The test suite, linting and type checking run on every Python version the
  package claims rather than only the one pinned for development. Two of the
  three advertised versions had never been run
- A scheduled job asks the live provider weekly whether it still serves what
  this version reads. Every other provider test uses a fixture or a mock, so
  all of them would keep passing if the format changed and the failure would
  reach a user before it reached the repository. It is excluded from the
  ordinary suite, so running the tests never depends on a network or on someone
  else's service being up

### Documented

- How to upgrade, which was never written down, and that upgrading is something
  you do rather than something that happens to you

## [0.3.0] - 2026-09-19

### Added

- The Markdown header names what the provider did not serve, rather than only
  counting it. A real Claude capture reported eleven withheld attachments on
  the terminal and in the JSON while the file most people read said nothing
  about them. Findings bearing on completeness are now listed there; findings
  about what this tool could not model stay counted, because they describe the
  extraction rather than the conversation and belong to the archival record.
  Observations of the same thing on different messages are merged and their
  counts summed, since the message id that separates them is not shown in a
  Markdown file and two identical lines read as a duplication bug
- Content whose type this version does not model shows the title and link it
  carried, where it carried them. Claude serves each web result a search
  returned as a block this version has no model for, and the export printed
  eighty-two identical placeholders in place of eighty-two distinct sources.
  No canonical block type was added: Grok's shared pages name the same field
  differently and Gemini's expose nothing comparable, so a model built from
  one provider's shape would be a guess with a schema bump attached. The
  keys are read generically and the complete block stays in the JSON. Nothing
  is fetched to do this

### Changed

- The terminal report prints how many times a collapsed finding was observed.
  One line reading `knowledge preserved verbatim` said the same thing whether
  it happened once or eighty-two times
- Publishing is gated on the test suite running against the tagged commit, and
  the build runs with no credential in scope. A tag can point at any commit,
  so the checks that ran on `main` verified a release only by coincidence

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
