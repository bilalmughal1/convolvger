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

## Supported Providers

Initial providers:

- ChatGPT
- Claude
- Gemini
- Grok

Additional providers will be added as their public sharing formats are supported and tested.

## Status

Convolvger is under active development. The project is not yet ready for general use.

## License

MIT
