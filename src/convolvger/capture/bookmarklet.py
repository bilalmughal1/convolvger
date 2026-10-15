"""The bookmarklet that hands a snapshot from the browser to the listener.

It runs on the share page itself, so the request for the snapshot is
the same request the page would have made: same origin, same session,
nothing impersonated. Then it posts what it read to the listener on
loopback.

Which pages hold a snapshot, and where, is declared by each provider
that is captured rather than fetched, and the bookmarklet tries those
declarations in turn. They are listed here explicitly, as providers are
registered: a second capture-only provider (Perplexity) is what turned
the one Claude rule into a list.
"""

import json

from convolvger.capture.rules import CaptureRule
from convolvger.capture.server import DEFAULT_PORT
from convolvger.providers.claude._urls import CAPTURE as CLAUDE
from convolvger.providers.perplexity._urls import CAPTURE as PERPLEXITY

RULES: tuple[CaptureRule, ...] = (CLAUDE, PERPLEXITY)

TEMPLATE = """\
javascript:(async()=>{{const R={rules};let r,m;\
for(const x of R){{if(x.h.includes(location.hostname)){{m=location.pathname.match(new RegExp(x.p));if(m){{r=x;break;}}}}}}\
if(!r){{alert('Convolvger: open a share page first, then click this.');return;}}\
const api=r.a.replace('{{share_id}}',m[1]);let t;\
try{{const q=await fetch(api,{{credentials:'include'}});\
if(!q.ok){{alert('Convolvger: the page would not give up its snapshot ('+q.status+').');return;}}\
t=await q.text();}}catch(e){{alert('Convolvger: could not read the snapshot. '+e);return;}}\
try{{const p=await fetch('http://127.0.0.1:{port}/',{{method:'POST',\
headers:{{'Content-Type':'application/json'}},\
body:JSON.stringify({{url:location.href,content:t}})}});\
alert(p.ok?'Convolvger: snapshot sent.':'Convolvger: the listener would not take it.');}}\
catch(e){{alert('Convolvger: nothing is listening on port {port}. Start the command first.');}}}})()\
"""


def bookmarklet(port: int = DEFAULT_PORT) -> str:
    """Return a ``javascript:`` link that captures the page it is clicked on.

    One line, and free of percent signs, because a browser decodes a
    ``javascript:`` URL before running it: an encoded sequence would be
    mangled and a newline would truncate the link when pasted. The rules
    are written as JSON, which is also JavaScript.
    """
    rules = json.dumps(
        [{"h": sorted(rule.hosts), "p": rule.path, "a": rule.api} for rule in RULES],
        separators=(",", ":"),
    )
    link = TEMPLATE.format(rules=rules, port=port)
    assert "\n" not in link, "a bookmarklet must be one line"
    assert "%" not in link, "a percent sign would be decoded before running"
    return link
