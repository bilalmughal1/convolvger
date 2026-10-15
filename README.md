# Convolvger

Local-first archival for public AI conversations.

Give Convolvger the share link of a conversation from ChatGPT, Claude, Gemini,
Grok, DeepSeek, Kimi, Qwen or Perplexity. It reads the conversation the link
publishes, checks what it could and could not extract, and writes it out as a
Markdown document to read and a JSON archive that keeps everything the
provider served. It runs on your machine, needs no account, and sends nothing
anywhere but the provider you asked it to read.

## Contents

- [Supported providers](#supported-providers)
- [Install](#install)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Capturing from your browser](#capturing-from-your-browser)
- [What the output contains](#what-the-output-contains)
- [Provider notes](#provider-notes)
- [Limits](#limits)
- [What a snapshot is](#what-a-snapshot-is)
- [Status](#status)

## Supported providers

| Provider | How it is read | Share link |
| --- | --- | --- |
| ChatGPT | fetched | `https://chatgpt.com/share/ID` |
| Claude | captured in your browser | `https://claude.ai/share/ID` |
| Gemini | fetched | `https://gemini.google.com/share/ID`, `https://g.co/gemini/share/ID`, `https://share.gemini.google/TOKEN` |
| Grok | fetched | `https://grok.com/share/ID` |
| DeepSeek | fetched | `https://chat.deepseek.com/share/ID` |
| Kimi | fetched | `https://www.kimi.ai/share/ID` (also `www.kimi.com`, `kimi.moonshot.cn`) |
| Qwen | fetched | `https://chat.qwen.ai/s/ID` (also `chat.qwenlm.ai`) |
| Perplexity | captured in your browser | `https://www.perplexity.ai/search/ID` |

*Fetched* means Convolvger asks for the conversation itself, as the share page
does, with no cookie or account. *Captured* means the provider refuses programs
that are not browsers, so Convolvger waits for your browser to hand the
conversation over instead of pretending to be one: see
[Capturing from your browser](#capturing-from-your-browser).

## Install

Convolvger needs Python 3.12 or newer. The simplest route is
[uv](https://docs.astral.sh/uv/), which downloads a suitable Python itself.

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

**Without uv**: `pipx install convolvger`, or `pip install convolvger` inside a
virtual environment running Python 3.12 or newer. An older interpreter fails
with `Requires-Python >=3.12`.

Check the install with `convolvger --version`. It prints the version, the
Python it runs on, the archive schema it writes and the ones it reads, and the
providers it supports. Include it in a bug report: the version it prints is the
one your archives record.

### Upgrade

Convolvger never updates itself and never checks for a new release, because a
tool that keeps your conversations on your machine has no business contacting
an index about itself. Upgrade with whatever installed it:

```
uv tool upgrade convolvger      # installed with uv
pipx upgrade convolvger         # installed with pipx
pip install -U convolvger       # inside a virtual environment
```

Releases are listed at
[github.com/fahadbilalsaleem/convolvger/releases](https://github.com/fahadbilalsaleem/convolvger/releases).

A newer Convolvger reads archives written by older ones: each archive records
its schema version, and `--version` lists the versions this one reads. The
reverse does not hold. Archive schema 4, which records each message's
citations, is refused by Convolvger 0.6 with a message naming the version.

## Quick start

```
convolvger inspect https://chatgpt.com/share/ID           # look, write nothing
convolvger export  https://chatgpt.com/share/ID           # write a Markdown document
convolvger export  https://chatgpt.com/share/ID -f json   # write the JSON archive
convolvger verify  conversation.json                      # check an archive
```

Always type `convolvger` first: a bare `export URL` runs your shell's own
`export` instead.

## Commands

**`convolvger providers`** lists the providers this build supports.

**`convolvger inspect URL`** prints the title, the provider, how many messages
there are and every finding about the extraction, and writes nothing.

**`convolvger export URL`** writes the conversation to a file in the current
directory, named after its title:

| Option | Effect |
| --- | --- |
| `-f md` (default) | The Markdown document, for reading |
| `-f json` | The JSON archive, the complete record |
| `-o PATH` | Write to `PATH`, replacing any file already there |
| `-o -` | Write to standard output |
| `--include-hidden` | Keep messages the provider hides from viewers (Markdown) |
| `--include-inactive` | Keep branches the conversation moved away from (Markdown) |
| `--from-file PATH` | Read a saved copy instead of fetching (see below) |
| `--capture` | Wait for your browser to hand the conversation over |

The file name keeps the letters, digits and accents of the title in any
script, so a title in Arabic, Chinese or Hindi gives a name in Arabic, Chinese
or Hindi; punctuation, symbols and emoji become hyphens. An existing file is
never replaced by a name Convolvger chose: the new one is numbered
(`title-2.md`, `title-3.md`). Output is written as UTF-8 whatever the system's
encoding. On Windows, prefer `-o file.md` to `-o -` with a PowerShell `>`,
which may re-encode the output.

**`--from-file`** parses a copy you saved instead of asking the provider:

```
convolvger export https://chatgpt.com/share/ID --from-file saved-page.html
```

The link is still given: it chooses the provider and is the source the archive
records. When a saved file was made cannot be known from the file, so its
archive records no retrieval time rather than a false one. The file is read as
UTF-8, or as UTF-8, UTF-16 or UTF-32 when it starts with the byte-order mark
that says so (as Notepad and Windows PowerShell 5.1 write them); any other
encoding is refused rather than guessed. Re-reading a saved copy is the way to
archive what you saw, since the provider's answer may since have changed.
`--from-file` works with `inspect` too.

**`convolvger verify ARCHIVE.json`** reads an archive and reports what it
records, without fetching or parsing anything again. It answers two questions
separately:

- *Complete*: did the provider serve everything its own snapshot referred to?
- *Faithful*: could everything it served be modelled?

A finding that bears on neither is listed but counted toward neither, so a
share whose messages are empty by design is still reported complete. A finding
code this version does not know changes neither answer, since a later version
may have written the archive, and an archive of a schema this version cannot
read is refused rather than judged.

**Exit codes**: `0` clean; `2` finished with warnings, or for `verify`, a check
did not pass; `1` failed, or for `verify`, the file is not an archive this
version can read.

## Capturing from your browser

Claude and Perplexity put their conversation data behind a bot wall: asked by
a program, the page and the data behind it answer with a refusal or a
challenge, whatever headers are sent. Convolvger does not impersonate a
browser to get past that. It waits for yours, which the provider already
lets in.

One-time setup:

```
convolvger bookmarklet
```

This prints a bookmarklet, a bookmark whose address is a small program, and
how to save it. Then, for each conversation:

```
convolvger export --capture
```

Open the share page and click the bookmark. The bookmarklet asks the provider
for the same data the page itself loads, using your own browser session, and
hands it to the waiting command. No link is typed: it arrives with the
conversation, from the page you clicked. `--capture` works with `inspect` too.

Capturing Claude was verified in Chrome, Edge and Firefox, and capturing
Perplexity in Chrome. The bookmarklet works in any browser that runs
bookmarklets and lets a page reach `localhost`.

If you would rather not run a listener, save the data yourself and use
`--from-file`, giving the share link as usual. For Claude, the data is at
`https://claude.ai/api/chat_snapshots/ID?rendering_mode=messages&render_all_tools=true`;
open that in your browser and save it.

**What the listener does, and does not.** While the command waits, it listens
on `127.0.0.1:23477`: on your machine only, not your network. It takes one
conversation, then stops, and gives up after three minutes. It accepts a
conversation only from a page whose origin matches the share link it claims to
come from, and only for a link a provider handles, so a page on another site
can neither forge a conversation nor end the wait. A connection that sends
nothing is dropped when the wait ends. What it does not defend against: a page
on the provider's own site could reach it during the seconds it runs, and so
could another program on your machine, which could equally write the archive
file directly. Nothing is sent anywhere else.

## What the output contains

**The Markdown document** is for reading. It starts with a header naming the
source, the provider and when it was retrieved, and what the provider did not
serve: attachments a message names but does not carry, results a tool call
referred to but left empty, and turns a captured thread did not include.
Findings about what this tool could not model are counted there, and recorded
in full in the JSON.

- **Messages** appear under headings by role. Messages the provider hides from
  viewers and branches the conversation moved away from are left out by
  default, and each omission is reported in the header.
- **Reasoning** that a provider shows beside an answer (ChatGPT, Kimi, Qwen)
  appears as a labelled quote, apart from the answer, so the two are never
  mistaken for each other.
- **Citations** from Grok, DeepSeek, Kimi, Qwen and Perplexity appear in the
  text as `[1]`, `[2]`, numbered in the order the answer first cites each
  source, and a **Sources** list under the answer links each one by its title.
  Only cited sources are listed: in the real shares measured, about a third of
  the search results an answer carried were cited. A citation that points at
  nothing is left as written and reported, and nothing inside code is ever
  taken for a citation. ChatGPT, Claude and Gemini citations are kept in the
  JSON but not yet listed.
- **Content this version does not model** is flagged, not dropped. Where such
  a block carries a title and a link, the document shows them; nothing is
  fetched to do so.

**The JSON archive** is the record. It omits nothing the provider served:
every message, including hidden ones and inactive branches, every search
result, cited or not, and everything a provider sent that the model has no
field for, kept under `provider_metadata`. Text that was changed for reading,
by citation markers for instance, is kept beside it exactly as served. Every
finding is recorded with a stable code and a level: a *note* does not change
the exit status, a *warning* does.

**Whoever shared the conversation.** Claude, Kimi, Qwen and Perplexity name the
account that shared it, by display name, account id, username or profile
picture depending on the provider. That is kept in the JSON archive, because
the archive drops nothing served, and never appears in the Markdown document.

## Provider notes

**ChatGPT.** The share page carries the conversation inside it, encoded; it is
decoded locally. Its thoughts and reasoning recaps are shown as reasoning.

**Claude.** Captured. Tool calls and their results are kept as such.

**Gemini.** The page is an application shell that loads its conversation
separately; Convolvger asks for that data. The third link form,
`share.gemini.google`, is a shortener whose token is not the conversation's
id, so it costs one extra request to resolve. Citations and the searches the
model ran are kept in the JSON. A deleted or unknown share answers with an
empty success rather than an error, and is reported as missing.

**Grok.** Each citation marker becomes a number, and the page it links to is
listed under the answer, titled from the matching web result; two citations of
one page share a number. Grok's reasoning trace is kept in the JSON and
reported as unmodelled: its steps mix searches and tool calls into the prose,
and its shape has been seen in one conversation only. Files and images a
message names are reported as not carried, since the share lists them without
serving them. A share that is gone, or that answers with a title and no
messages, is reported as missing.

**DeepSeek.** Citations written `[citation:3]` are numbered and listed. Every
share carries the generic title "Shared Conversation", recorded as served. An
unknown share answers successfully with an error inside, and is reported as
missing.

**Kimi.** Its citations sit beside the text rather than in it, so the text is
left as served and the results they name are listed under it. Its reasoning is
shown as reasoning. A search the model ran is kept and reported as unmodelled.

**Qwen.** Citations written `[[3]]` are numbered across every search in the
answer and listed; `x = [[3]]` inside code is a nested list and left alone.
Each pair of reasoning title and thought is shown as reasoning.

**Perplexity.** Captured. The answer is assembled from the pieces Perplexity
splits it into, and its citations are read from the results Perplexity itself
marks as cited. A thread longer than twenty turns arrives in pages and only
the first page is captured; when more exist, the archive says so. An image
inside an answer is kept in the JSON and reported as unmodelled.

**Reasoning, in general.** Reasoning is shown only in the shape measured in
real shares; reasoning in any other shape is kept in the JSON and reported as a
warning. DeepSeek's reasoning has not been seen in a share yet and would be
kept and reported the same way.

## Limits

Convolvger refuses rather than misreads:

- A response, a captured conversation or a saved file larger than 32 MiB, and
  a ChatGPT page whose decoded data would unfold to more than that.
- JSON nested more than 64 levels deep (512 for an archive given to `verify`).
  The deepest real share measured nests 24.
- A saved file in an encoding other than UTF-8, UTF-16 or UTF-32.

Each refusal ends with an error message, not a traceback, and writes no file.

## What a snapshot is

Convolvger archives *public share snapshots*: what a provider chooses to show
at a link at a given moment. That is not the conversation itself, and not a
guarantee.

Share pages change after they are published. While building the ChatGPT
adapter we fetched the same link twice, eight hours apart. Both had the same
conversation, the same title and the same 31 message ids. The second time,
four messages addressed to a tool came back with their content emptied and
relabelled from `code` to `text`, while every id, role, status and metadata key
stayed the same. A comparison of anything but the content would have called
the two the same file. Nothing about the conversation had changed; the
provider's rendering of it had.

That is why every export records when it was retrieved, reports what it could
not render, and never silently drops content. An archive is a claim about what
was there when you looked, and it is only trustworthy if it also says when you
looked and what it could not see.

Convolvger does not recover private conversations, hidden model state, deleted
content, or attachments the provider does not publish. If it is not in the
snapshot, it is not in the archive.

## Status

Convolvger is in active development; every command above works today, and each
provider is checked against a real share. It is built to:

- archive public AI conversations locally, with no account and no telemetry;
- support many providers through isolated adapters;
- keep the structure and content a provider exposes, and say what it could not;
- produce the same output for the same input, whichever provider it came from;
- run entirely locally, with no language model involved.

## License

MIT
