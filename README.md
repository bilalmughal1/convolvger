# Convolvger

Local-first, provider-independent archival for public AI conversations.

Convolvger takes a public AI conversation share URL, reconstructs the conversation into a canonical internal model, validates the extracted data, and exports it into portable formats such as Markdown and JSON.

## Install

or `pip install convolvger`. Requires Python 3.12 or newer.

## Goals

- Archive public AI conversations locally
- Support multiple AI providers through isolated adapters
- Preserve conversation structure and exposed content
- Detect incomplete or inconsistent extraction
- Produce deterministic, provider-independent output
- Keep conversion entirely local, with no LLM required
- Avoid account credentials and telemetry

## What a snapshot is

Convolvger archives *public share snapshots*. A snapshot is what a provider chooses to expose at a given URL at a given moment — not the conversation itself, and not a guarantee.

Share pages can change after they are published. While building the ChatGPT adapter we fetched the same share link twice, eight hours apart. Both responses had the same conversation, the same title, and the same 31 message IDs. Four assistant messages addressed to a tool were served the second time with their payload emptied and their content type relabelled from `code` to `text` — while their IDs, roles, recipients, statuses, weights and every metadata key stayed identical. A comparison of anything but the content would have called the two snapshots the same file. Nothing about the conversation had changed; the provider's rendering of it had.

That is why every Convolvger export records when it was retrieved, reports every message it could not render, and never silently drops content. An archive is a claim about what was there when you looked. It is only trustworthy if it also says when it looked and what it could not see.

Convolvger does not recover private conversations, hidden model state, chain-of-thought, deleted content, or attachments the provider does not publish. If it is not in the snapshot, it is not in the archive.

## Supported Providers

Initial providers:

- ChatGPT
- Claude
- Gemini
- Grok

Additional providers will be added as their public sharing formats are supported and tested.

## Status

Convolvger is under active development and not yet ready for general use.

Working today: `convolvger providers`, `convolvger inspect URL`, `convolvger export URL` with `-o PATH` or `-o -` for stdout, `-f md` or `-f json`, plus `--include-hidden` and `--include-inactive`, and `convolvger verify PATH`.

ChatGPT share links can be fetched, parsed, and exported. Markdown is a reader-facing document that may omit content and reports every omission in its header; JSON is the complete archival record and omits nothing the model holds. The remaining providers are not implemented yet.

Extraction records structured findings, each with a stable code and a level. A note is recorded but does not change the exit status; a warning does. Both are written into the JSON archive either way, so nothing is withheld from the record because it was judged unremarkable.

`convolvger verify PATH` reads a JSON archive and reports what it records, without re-fetching or re-parsing anything. It answers two questions separately: whether the provider served everything its own snapshot structure referenced, and whether everything it served could be modelled. Findings that indicate neither are listed in full and counted toward neither answer, so an archive whose messages are mostly empty by design — which is how a public share snapshot normally arrives — is still reported complete. A finding whose code this version does not recognise changes no answer, since an archive may have been written by a later version. An archive declaring a schema version this version cannot read is refused rather than given a verdict.

Exit codes: 0 clean, 2 completed with warnings, 1 failed. For `verify`, 2 means a check did not pass, and 1 means the file could not be read as an archive at all.

## License

MIT
