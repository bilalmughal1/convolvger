# Convolvger

Local-first, provider-independent archival for public AI conversations.

Convolvger takes a public AI conversation share URL, reconstructs the conversation into a canonical internal model, validates the extracted data, and exports it into portable formats such as Markdown and JSON.

## Install

Convolvger needs Python 3.12 or newer. The simplest route is [uv](https://docs.astral.sh/uv/),
which downloads a suitable Python itself if you do not have one.

**macOS, Linux, WSL**

```
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool install convolvger
```

**Windows** (PowerShell)

```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv tool install convolvger
```

**Without uv**

```
pipx install convolvger
```

or `pip install convolvger` inside a virtual environment running Python 3.12 or
newer. Installing with an older interpreter fails with `Requires-Python >=3.12`,
which is the error to expect on a system Python 3.10 or 3.11.

Check the install:

```
convolvger --help
```

## Usage

Every command begins with `convolvger`, followed by a subcommand. There are
five: `providers`, `bookmarklet`, `inspect`, `export` and `verify`. Note that a bare
`export <url>` runs your shell's own `export` builtin rather than this tool.

**See which providers are supported**

```
convolvger providers
```

**Look at a conversation without saving anything**

```
convolvger inspect https://chatgpt.com/share/SHARE_ID
```

Prints the title, provider, message counts and every extraction finding, then
exits without writing a file.

**Export it**

```
convolvger export https://chatgpt.com/share/SHARE_ID
```

Writes Markdown to a filename derived from the conversation title, in the
current directory. To choose the format or the destination:

```
convolvger export https://chatgpt.com/share/SHARE_ID -f json
convolvger export https://chatgpt.com/share/SHARE_ID -o mychat.md
convolvger export https://chatgpt.com/share/SHARE_ID -o -
```

`-f json` writes the archival record; `-f md` (the default) writes the
reader-facing document. `-o -` writes to stdout instead of a file.

**Parse a snapshot you already saved**

```
convolvger export https://chatgpt.com/share/SHARE_ID --from-file saved-page.html
```

`--from-file` parses a saved copy of the share page instead of fetching the URL.
The URL is still required: it routes the snapshot to the right provider, and it
is the provenance the archive records. Because when a saved file was captured is
not knowable from the file, an archive made this way records no retrieval time
rather than claiming a false one.

This is how to re-read a capture without asking the provider for it again, which
matters because the answer may have changed since. It works with `inspect` too.

**Archive a Claude conversation**

A Claude share page cannot be fetched. The page loads its conversation
separately, and the service refuses non-browser clients whatever headers they
send. Rather than impersonate a browser, Convolvger waits for yours to hand the
snapshot over. One-time setup:

```
convolvger bookmarklet
```

That prints a bookmarklet and how to save it. Then, for any Claude share link:

```
convolvger export --capture
```

Open the share page and click the bookmark. The archive is written and named
after the conversation's own title. No URL is typed: it arrives with the
snapshot, from the page you clicked. `--capture` works with `inspect` too.

Verified in Chrome, Edge and Firefox. Other browsers should work where they run
bookmarklets and permit connections to localhost.

If you would rather not run a listener, `convolvger export <claude-share-url>`
prints the URL your browser can read the snapshot from. Open it, save the JSON,
and pass it with `--from-file`. That path works in any browser.

**What capturing does, and what it does not**

While the command waits it listens on `127.0.0.1:23477` — loopback only, not
reachable from your network. It takes one snapshot and then stops, and gives up
after three minutes. It accepts a payload only when the browser's origin matches
the address the payload claims to come from, so a page on another site cannot
post a forged conversation.

Two things it does not defend against, stated plainly: any page on the
provider's own domain could reach the listener during the seconds it runs, and
so could another program on your machine — though such a program could write the
archive file directly anyway. Nothing is transmitted anywhere else. Your browser
talks to the provider using the session it already has, and to loopback.

**What a Claude archive contains**

Claude's snapshot names the account that shared it, so a Claude JSON archive
carries `created_by` and `creator` — a display name and an account id — under
`provider_metadata`. They are kept because the JSON is the archival record and
drops nothing the provider served. No renderer reads `provider_metadata`, so
the Markdown export does not contain them.

Markdown omits provider-hidden messages and deactivated branches by default and
reports each omission in its header. `--include-hidden` and
`--include-inactive` keep them. Both flags are ignored for JSON, which never
omits anything.

The header also names what the provider itself did not serve: attachments a
message declared but did not carry, and tool results the snapshot referenced
and left empty. Observations of the same thing across messages are merged for
display and their counts summed, since the message id that separates them in
the record is not shown in a Markdown file. Findings about what this tool
could not model are counted in the header rather than named, and every finding
is recorded in full in the JSON export.

Content whose type this version does not model is flagged rather than dropped,
and where such a block carries a title and a link — a web result a search tool
returned, for instance — the export shows them. The complete block stays in
the JSON. Nothing is fetched to do this: the title and the link were served
inside the snapshot, and Convolvger never dereferences a URL it archives.

**Check an archive's integrity**

```
convolvger verify mychat.json
```

Reads a JSON archive and reports what it records, without re-fetching or
re-parsing anything. See the Status section below for what the two verdicts
mean.

**Exit codes**

`0` clean, `2` completed with warnings or with a failed integrity check, `1`
failed.

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

- ChatGPT — fetched directly from a share link
- Claude — captured from your own browser, since its share pages cannot be
  fetched
- Gemini — not implemented yet
- Grok — not implemented yet

Additional providers will be added as their public sharing formats are supported and tested.

## Status

Convolvger is under active development and not yet ready for general use.

Every command shown under Usage above works today.

ChatGPT share links can be fetched, parsed, and exported. Markdown is a reader-facing document that may omit content, reports every omission in its header, and names what the provider did not serve; JSON is the complete archival record and omits nothing the model holds.

Claude share snapshots can be parsed and exported, but not fetched: the service refuses non-browser clients, so a snapshot is captured from your own browser as described under Usage. Gemini and Grok are not implemented yet.

Extraction records structured findings, each with a stable code and a level. A note is recorded but does not change the exit status; a warning does. Both are written into the JSON archive either way, so nothing is withheld from the record because it was judged unremarkable.

`convolvger verify PATH` reads a JSON archive and reports what it records, without re-fetching or re-parsing anything. It answers two questions separately: whether the provider served everything its own snapshot structure referenced, and whether everything it served could be modelled. Findings that indicate neither are listed in full and counted toward neither answer, so an archive whose messages are mostly empty by design — which is how a public share snapshot normally arrives — is still reported complete. A finding whose code this version does not recognise changes no answer, since an archive may have been written by a later version. An archive declaring a schema version this version cannot read is refused rather than given a verdict.

Exit codes: 0 clean, 2 completed with warnings, 1 failed. For `verify`, 2 means a check did not pass, and 1 means the file could not be read as an archive at all.

## License

MIT
