# Convolvger

Local-first, provider-independent archival for public AI conversations.

Convolvger takes a public AI conversation share URL, reconstructs the conversation into a canonical internal model, validates the extracted data, and exports it into portable formats such as Markdown and JSON.

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

Share pages can change after they are published. While building the ChatGPT adapter we fetched the same share link twice, eight hours apart. Both responses had the same conversation, the same title, and the same 31 message IDs — but four tool-call blocks present in the first fetch came back empty in the second. Nothing about the conversation had changed; the provider's rendering of it had.

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

Working today: `convolvger providers`, `convolvger inspect URL`, and `convolvger export URL` with `-o PATH` or `-o -` for stdout, plus `--include-hidden` and `--include-inactive`.

ChatGPT share links can be fetched, parsed, and exported to Markdown. JSON export, integrity validation, and the remaining providers are not implemented yet.

Exit codes: 0 clean, 2 completed with warnings, 1 failed.

## License

MIT
