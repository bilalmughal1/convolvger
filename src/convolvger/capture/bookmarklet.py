"""The bookmarklet that hands a snapshot from the browser to the listener.

It runs on the share page itself, so the request for the snapshot is
the same request the page would have made: same origin, same session,
nothing impersonated. Then it posts what it read to the listener on
loopback.

The rule it carries -- which pages hold a snapshot and where -- comes
from the provider that knows. Only one provider needs this today, so
the rule is imported directly rather than reached through a capability
every provider would have to answer. When a second provider needs
capturing, that is the moment to decide what the shared shape is; a
single caller is not enough evidence to design one.
"""

from convolvger.capture.server import DEFAULT_PORT
from convolvger.providers.claude._urls import SHARE_HOSTS, SNAPSHOT_API

TEMPLATE = """\
javascript:(async()=>{{const H={hosts};const m=location.pathname.match(/^\\/share\\/([^\\/?#]+)/);\
if(!H.includes(location.hostname)||!m){{alert('Convolvger: open a share page first, then click this.');return;}}\
const api='{api}'.replace('{{share_id}}',m[1]);let t;\
try{{const r=await fetch(api,{{credentials:'include'}});\
if(!r.ok){{alert('Convolvger: the page would not give up its snapshot ('+r.status+').');return;}}\
t=await r.text();}}catch(e){{alert('Convolvger: could not read the snapshot. '+e);return;}}\
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
    mangled and a newline would truncate the link when pasted.
    """
    hosts = "[" + ",".join(f"'{host}'" for host in sorted(SHARE_HOSTS)) + "]"
    link = TEMPLATE.format(hosts=hosts, api=SNAPSHOT_API, port=port)
    assert "\n" not in link, "a bookmarklet must be one line"
    assert "%" not in link, "a percent sign would be decoded before running"
    return link
