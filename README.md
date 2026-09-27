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
convolvger --version
```

`--version` reports the installed version, the interpreter it runs on, the
archive schema it writes and the ones it can read, and the providers this build
supports. It is the quickest thing to include in a bug report, because the
version it prints is the one your archives record.

## Upgrade

Convolvger never updates itself and never checks for a new release. A tool that
keeps your conversations on your machine has no business contacting an index to
ask about itself, so upgrading is something you do deliberately, with whichever
tool installed it:

```
uv tool upgrade convolvger      # if you installed with uv
pipx upgrade convolvger         # if you installed with pipx
pip install -U convolvger       # inside a virtual environment
```

Then run `convolvger --version` to confirm which copy you now have. Releases are
listed at [github.com/bilalmughal1/convolvger/releases](https://github.com/bilalmughal1/convolvger/releases).

Archives written by an older version stay readable: each one records the schema
it was written against, and a newer Convolvger reads the versions it lists under
`--version` rather than assuming.

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

Writes Markdown to a file named after the conversation's title, in the
current directory. The name keeps the letters, digits and accents of the
title in any script, so a conversation titled in Arabic, Chinese or Hindi is
named in Arabic, Chinese or Hindi; punctuation, symbols and emoji become
hyphens. If that file already
exists, the new one is numbered (`title-2.md`, `title-3.md`) rather than
replacing it. To choose the format or the destination:

```
convolvger export https://chatgpt.com/share/SHARE_ID -f json
convolvger export https://chatgpt.com/share/SHARE_ID -o mychat.md
convolvger export https://chatgpt.com/share/SHARE_ID -o -
```

`-f json` writes the archival record; `-f md` (the default) writes the
reader-facing document. `-o -` writes to stdout instead of a file. A path you
choose with `-o` is written as asked, replacing any file already there.

Files are written as UTF-8 whatever language the conversation is in, and so
is `-o -` when its output goes to a file or another program, even where the
system's own encoding is not UTF-8. On Windows, prefer `-o file.md` to `-o -`
with a PowerShell redirect: PowerShell may re-encode a program's output
before its `>` writes it.

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

The saved file is read as UTF-8, or as UTF-8, UTF-16 or UTF-32 when it begins
with the byte-order mark that says so, which is what Notepad and Windows
PowerShell 5.1 write. A file in any other encoding is refused with a message
rather than guessed at, because a wrong guess turns the text into different
text.

**Archive a Gemini conversation**

```
convolvger export https://gemini.google.com/share/SHARE_ID
```

Gemini share pages are fetched directly, with no browser involved. The page
itself carries no conversation — it is an application shell that loads one
afterwards — so Convolvger asks for the same data the page does. All three link
forms work:

```
https://gemini.google.com/share/SHARE_ID
https://g.co/gemini/share/SHARE_ID
https://share.gemini.google/TOKEN
```

The first two carry the conversation id. The third is a shortener whose token is
not the id, so that form costs one extra request to resolve.

A Gemini conversation may cite web pages and record the searches the model ran.
Neither appears in the answer text the provider serves, so both are kept in the
JSON archive under `provider_metadata`, alongside the response ids. As with
Claude, no renderer reads `provider_metadata` and none of it reaches Markdown.

A deleted or unknown Gemini share answers with a success status and an empty
payload rather than an error, so Convolvger reports it as a missing share
instead of passing an empty conversation off as a real one.

**Archive a Grok conversation**

```
convolvger export https://grok.com/share/SHARE_ID
```

Grok share pages are fetched directly, with no browser involved. Like Gemini's,
the page loads its conversation separately, so Convolvger asks for the same
JSON the page does. No cookie or account is needed. The share id is taken as
it appears in the link, whatever its prefix.

A Grok answer marks its citations inline. Those markers are lifted out of the
text so they do not clutter the document; the JSON archive keeps the message
exactly as served, alongside the web results, X posts, citation cards and
model name the provider served. None of it reaches Markdown. The reasoning
trace Grok shows beside a thinking answer is kept in the JSON too, but this
version does not model it, so it is reported as a warning rather than passed
over. Files and images a message names are reported as not carried: the
share lists them without serving them, and Convolvger does not follow their
links to fetch them.

A Grok share that no longer exists answers with an error, but a share can also
answer successfully with its title and no messages. Both are reported as a
missing share rather than exported as an empty conversation.

**Archive a DeepSeek, Kimi or Qwen conversation**

```
convolvger export https://chat.deepseek.com/share/SHARE_ID
convolvger export https://www.kimi.ai/share/SHARE_ID
convolvger export https://chat.qwen.ai/s/SHARE_ID
```

All three are fetched directly, with no browser involved: each share page
loads its conversation from an endpoint that answers this tool's own
User-Agent with no cookie or account, and Convolvger asks it directly.
`www.kimi.com` and `kimi.moonshot.cn` share links work as well as
`www.kimi.ai`, and so do `chat.qwenlm.ai` links for Qwen.

DeepSeek and Qwen number their citations inside the answer text
(`[citation:3]`, `[[3]]`). A number that points at a search result the share
carries is taken out of the text so the document reads cleanly, and the
answer exactly as served is kept in the JSON archive beside it, with the
search results. A number that points at nothing is left in place and
reported, and a number inside code is never touched: `x = [[3]]` is a
nested list, not a citation. Kimi marks citations beside the text rather
than inside it, so its text needs no change. None of the citations or search
results reach Markdown.

Kimi and Qwen show the model's reasoning beside an answer. It is kept in the
JSON archive, but this version does not model it, so it is reported as a
warning rather than passed over, as Grok's is. DeepSeek's reasoning has not
been seen in a share yet; if one carries it, it is kept and reported the same
way.

A Kimi share names the account that shared it, and a Qwen share carries the
sharer's account id. Both are kept in the JSON archive under
`provider_metadata`, as Claude's `creator` is, and neither reaches Markdown.

A DeepSeek share carries a generic title, "Shared Conversation", rather than
the conversation's own, and the archive records it as served. An unknown
DeepSeek or Qwen share id answers successfully with an error inside, and an
unknown Kimi one answers 404; all three are reported as a missing share. A
share that was deleted has not been tried and is assumed to answer the same.

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
- Gemini — fetched directly from a share link
- Grok — fetched directly from a share link
- DeepSeek — fetched directly from a share link
- Kimi — fetched directly from a share link
- Qwen — fetched directly from a share link

Additional providers will be added as their public sharing formats are supported and tested.

## Status

Convolvger is under active development and not yet ready for general use.

Every command shown under Usage above works today.

ChatGPT share links can be fetched, parsed, and exported. Markdown is a reader-facing document that may omit content, reports every omission in its header, and names what the provider did not serve; JSON is the complete archival record and omits nothing the model holds.

Claude share snapshots can be parsed and exported, but not fetched: the service refuses non-browser clients, so a snapshot is captured from your own browser as described under Usage.

Gemini share links can be fetched, parsed and exported, in all three of the link forms Google issues. Citations and search queries are preserved in the JSON archive rather than rendered into the document.

Grok share links can be fetched, parsed and exported. Inline citations, search results and X posts are preserved in the JSON archive rather than rendered into the document; the reasoning trace is preserved but not yet modelled, and is reported as such.

DeepSeek, Kimi and Qwen share links can be fetched, parsed and exported. Citations and search results are preserved in the JSON archive rather than rendered into the document, and inline citation numbers are taken out of the text only where they resolve. Kimi's and Qwen's reasoning is preserved but not yet modelled, and is reported as such.

Extraction records structured findings, each with a stable code and a level. A note is recorded but does not change the exit status; a warning does. Both are written into the JSON archive either way, so nothing is withheld from the record because it was judged unremarkable.

`convolvger verify PATH` reads a JSON archive and reports what it records, without re-fetching or re-parsing anything. It answers two questions separately: whether the provider served everything its own snapshot structure referenced, and whether everything it served could be modelled. Findings that indicate neither are listed in full and counted toward neither answer, so an archive whose messages are mostly empty by design — which is how a public share snapshot normally arrives — is still reported complete. A finding whose code this version does not recognise changes no answer, since an archive may have been written by a later version. An archive declaring a schema version this version cannot read is refused rather than given a verdict.

Exit codes: 0 clean, 2 completed with warnings, 1 failed. For `verify`, 2 means a check did not pass, and 1 means the file could not be read as an archive at all.

## License

MIT
