"""
Build the Chadwick Institute Young Nuclear Network website into site/.

    python build_site.py              scrape the event and conference sources, then build every page
    python build_site.py --offline    build from the last scrape (site/events.json), without going online

What goes where
    site.json                   names, the network's email (where the forms' emails go), Linktree, web address
    content/events/*.md         our own events
    content/news/*.md           news posts
    content/articles/*.md       articles by members
    content/opportunities/*.md  PhDs, jobs and placements (each drops off the site after its closing date)
    content/conferences.csv     conferences the committee adds by hand (dated)
    content/conference_series.csv   the directory of major conference series, by field
    content/images/             pictures used in posts and articles
    assets/                     style.css, site.js
Files whose names start with _ are skipped. See README.md for the header each kind of file needs.

The site is static: no database, no cookies, no analytics, no scripts from other sites. Sign-ups go to
an email the visitor sends from their own email app to the network's mailbox, so no personal data is handled by
the website, GitHub or any form service.
"""
import csv
import datetime as dt
import html
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "site"
CONTENT = HERE / "content"
TODAY = dt.date.today()
CFG = json.loads((HERE / "site.json").read_text(encoding="utf-8"))
esc = html.escape


# --------------------------------------------------------------------------- content files
def read_md(path: Path) -> dict:
    """A content file: a '---' header of 'key: value' lines, then Markdown."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta, body = {}, text
    if text.startswith("---\n"):
        head, _, body = text[4:].partition("\n---\n")
        for line in head.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    meta["body"] = body.strip()
    meta["slug"] = path.stem
    return meta


def load(kind: str) -> list[dict]:
    folder = CONTENT / kind
    return [read_md(p) for p in sorted(folder.glob("*.md")) if not p.name.startswith("_")] if folder.exists() else []


def date_of(s: str):
    try:
        return dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- a small, safe Markdown
SAFE_URL = re.compile(r"^(https?://|mailto:|#|\.{0,2}/|[\w.-]+(/|\.html|\.jpe?g|\.png|\.webp|\.svg|#|$))", re.I)


def inline(s: str) -> str:
    """Escape everything first, then turn back on only links, images, bold and italic."""
    s = esc(s, quote=True)

    def link(m, image=False):
        label, url = m.group(1), html.unescape(m.group(2)).strip()
        if not SAFE_URL.match(url):
            return label
        u = esc(url, quote=True)
        if image:
            return f'<img src="{u}" alt="{label}" loading="lazy">'
        ext = ' target="_blank" rel="noopener noreferrer"' if url.startswith("http") else ""
        return f'<a href="{u}"{ext}>{label}</a>'
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", lambda m: link(m, True), s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return s


def markdown(text: str) -> str:
    """Paragraphs, ## and ### headings, - and 1. lists, > quotes. Raw HTML is shown as text, never run."""
    out, para, items, kind = [], [], [], None

    def flush():
        nonlocal para, items, kind
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
        if items:
            out.append(f"<{kind}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{kind}>")
        para, items, kind = [], [], None

    for line in text.splitlines():
        s = line.strip()
        if not s:
            flush()
        elif m := re.match(r"(#{2,3})\s+(.*)", s):
            flush()
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif m := re.match(r"[-*]\s+(.*)", s):
            if kind != "ul":
                flush()
                kind = "ul"
            items.append(m.group(1))
        elif m := re.match(r"\d+[.)]\s+(.*)", s):
            if kind != "ol":
                flush()
                kind = "ol"
            items.append(m.group(1))
        elif s.startswith(">"):
            flush()
            out.append(f"<blockquote><p>{inline(s.lstrip('> '))}</p></blockquote>")
        elif items:
            items[-1] += " " + s
        else:
            para.append(s)
    flush()
    return "\n".join(out)


# --------------------------------------------------------------------------- dates
def fmt(d: dt.date, weekday=True) -> str:
    return d.strftime("%a %d %b %Y" if weekday else "%d %B %Y").replace(" 0", " ").lstrip("0")


def span(s: dt.date, f: dt.date) -> str:
    return fmt(s) if s == f else f"{fmt(s)} to {fmt(f)}"


def date_box(s: dt.date | None, f: dt.date | None = None, tbc=False) -> str:
    if tbc or not s:
        return '<div class="date" aria-hidden="true"><b>TBC</b><span>date</span></div>'
    f = f or s
    if s == f:
        top, bottom = f"{s.day}", s.strftime("%b")
    elif (s.year, s.month) == (f.year, f.month):
        top, bottom = f"{s.day}–{f.day}", s.strftime("%b")
    else:
        top, bottom = f"{s.day}", f"{s.strftime('%b')}–{f.strftime('%b')}"
    return f'<div class="date" aria-hidden="true"><b>{top}</b><span>{bottom}</span></div>'


# --------------------------------------------------------------------------- shared pieces
LOGO = ('<svg viewBox="-1.3 -1.1 2.9 2.2" aria-hidden="true" focusable="false">'
        '<path fill="#FFFFFF" d="M0.568 -0.616 A1 1 0 1 0 0.568 0.616 L0.332 0.431 A0.7 0.7 0 1 1 0.332 -0.431 Z"/>'
        '<circle cx="-0.22" cy="0" r="0.3" fill="#E0B64A"/><circle cx="0.42" cy="0" r="0.085" fill="#E0B64A"/>'
        '<circle cx="0.70" cy="0" r="0.07" fill="#E0B64A"/><circle cx="0.96" cy="0" r="0.055" fill="#E0B64A"/>'
        '<circle cx="1.20" cy="0" r="0.04" fill="#E0B64A"/></svg>')

MARK = ('<svg class="mark" viewBox="-1.3 -1.1 2.9 2.2" aria-hidden="true" focusable="false">'
        '<path class="ring" d="M0.568 -0.616 A1 1 0 1 0 0.568 0.616 L0.332 0.431 A0.7 0.7 0 1 1 0.332 -0.431 Z"/>'
        '<circle class="dot" cx="-0.22" cy="0" r="0.3"/>'
        '<circle class="dot trail" cx="0.42" cy="0" r="0.085"/><circle class="dot trail" cx="0.70" cy="0" r="0.07"/>'
        '<circle class="dot trail" cx="0.96" cy="0" r="0.055"/><circle class="dot trail" cx="1.20" cy="0" r="0.04"/>'
        '<circle class="dot trail" cx="1.40" cy="0" r="0.028"/></svg>')

TRAIL = '<span class="trail" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'

NAV = [("index.html", "Home"), ("events.html", "Events"), ("conferences.html", "Conferences"),
       ("news.html", "News"), ("articles.html", "Articles"), ("opportunities.html", "Opportunities"),
       ("partners.html", "Work with us"), ("research.html", "Research"), ("about.html", "About"), ("members.html", "Members")]

sys.path.insert(0, str(HERE))
import geomap  # noqa: E402  (the conference map)

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'self'; form-action 'none'")

FONTS = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600&"
         "family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap")


def ext(url: str) -> str:
    """Attributes for a link that leaves the site."""
    return ' target="_blank" rel="noopener noreferrer"' if url.startswith("http") else ""


def email_block(label="Email us") -> str:
    e = esc(CFG["email"])
    return (f'<p class="copy"><span>{label}:</span> <a href="mailto:{e}"><code>{e}</code></a>'
            f'<button type="button" data-copy="{e}">Copy</button></p>')


def accounts_on() -> bool:
    return CFG.get("supabase_url", "").startswith("https://") and bool(CFG.get("supabase_anon_key"))


def mail_form(fid: str, subject: str, subject_field: str, fields: list, send: str, note: str = "") -> str:
    """An on-page form that, on Send, opens the visitor's email app with everything filled in, addressed to
    the network. Nothing is sent or stored by the website. fields: (name, label, kind, required, options)
    with kind text | email | url | tel | select | checks | area | agree."""
    rows = []
    for name, label, kind, req, opts in fields:
        r = " required" if req else ""
        star = "" if req or kind == "agree" else ' <span class="opt">(optional)</span>'
        fid_n = f"{fid}-{name}"
        if kind == "select":
            o = "".join(f"<option>{esc(x)}</option>" for x in opts)
            rows.append(f'<label class="field" for="{fid_n}"><span>{esc(label)}{star}</span>'
                        f'<select id="{fid_n}" name="{esc(label)}"{r}><option value="">Choose one</option>{o}</select></label>')
        elif kind == "checks":
            o = "".join(f'<label><input type="checkbox" name="{esc(label)}" value="{esc(x)}"> {esc(x)}</label>' for x in opts)
            rows.append(f'<fieldset class="field"><legend>{esc(label)}{star}</legend><div class="boxes">{o}</div></fieldset>')
        elif kind == "area":
            rows.append(f'<label class="field wide" for="{fid_n}"><span>{esc(label)}{star}</span>'
                        f'<textarea id="{fid_n}" name="{esc(label)}" rows="4"{r}></textarea></label>')
        elif kind == "agree":
            rows.append(f'<label class="agree wide"><input type="checkbox" name="{esc(label)}" value="Yes"{r}> <span>{esc(label)}</span></label>')
        else:
            auto = {"email": "email", "tel": "tel", "url": "url"}.get(kind, "")
            ac = {"Full name": "name", "Contact name": "name", "Name": "name", "Email": "email", "Phone": "tel",
                  "Organisation": "organization", "Job title": "organization-title"}.get(label, "off")
            rows.append(f'<label class="field" for="{fid_n}"><span>{esc(label)}{star}</span>'
                        f'<input id="{fid_n}" name="{esc(label)}" type="{auto or "text"}" autocomplete="{ac}"{r}></label>')
    e = esc(CFG["email"])
    return f"""<form class="mailform" id="{fid}" data-mailform data-to="{e}" data-subject="{esc(subject)}" data-subject-field="{esc(subject_field)}" novalidate>
  <div class="grid">{''.join(rows)}</div>
  {f'<p class="small muted">{note}</p>' if note else ''}
  <div class="actions"><button class="btn btn-navy" type="submit">{esc(send)}</button></div>
  <p class="form-error hidden" role="alert" data-error>Please fill in the boxes marked in gold.</p>
  <div class="sent hidden" role="status" data-sent>
    <p><strong>Your email app should now be open with this message ready.</strong> Check it, then press send there.
      Nothing goes to us until you do.</p>
    <p class="small">No email app opened? Copy the message and send it to <code>{e}</code> yourself.</p>
    <div class="actions"><button class="btn btn-line" type="button" data-copy-form>Copy the message</button></div>
  </div>
  <noscript><p class="note">This form needs JavaScript. You can email us instead at {e}.</p></noscript>
</form>"""


JOIN_FIELDS = [
    ("name", "Full name", "text", True, None),
    ("email", "Email", "email", True, None),
    ("status", "I am", "select", True, ["An undergraduate", "An MSc student", "A PhD, MPhil or MRes student", "A postdoc",
                                         "University staff", "Working in industry", "Other"]),
    ("dept", "Department or organisation", "text", True, None),
    ("interests", "I'm interested in", "checks", False, ["Radiation detection", "Radiation protection", "Fusion",
        "Reactor physics", "Nuclear materials", "Decommissioning and waste", "Nuclear medicine",
        "Nuclear data and modelling", "Policy", "Careers and industry"]),
    ("more", "Anything else you'd like us to know", "area", False, None),
    ("consent", "I agree to the network keeping these details to send me news of its events and opportunities. "
                "I can unsubscribe at any time.", "agree", True, None),
]
PARTNER_FIELDS = [
    ("name", "Your name", "text", True, None),
    ("email", "Email", "email", True, None),
    ("org", "Organisation", "text", True, None),
    ("title", "Job title", "text", False, None),
    ("help", "I'd like to", "checks", False, ["Give a talk", "Run a workshop or careers session", "Host a visit",
        "Share an opportunity", "Mentor someone", "Support an event", "Help with the summer school", "Talk it through first"]),
    ("how", "In person or online", "select", False, ["In person", "Online", "Either"]),
    ("when", "Roughly when suits you", "text", False, None),
    ("details", "Anything else: a topic, an idea, a question", "area", False, None),
    ("thanks", "You may thank us by name on the website and LinkedIn.", "agree", False, None),
    ("consent", "You may contact me about this.", "agree", True, None),
]
PAPER_FIELDS = [
    ("name", "Your name", "text", True, None),
    ("email", "Email", "email", True, None),
    ("title", "Title", "text", True, None),
    ("authors", "Authors", "text", True, None),
    ("link", "Link (DOI, arXiv or journal page)", "url", False, None),
    ("kind", "What it is", "select", True, ["Journal paper", "Preprint", "Conference paper or poster", "Report", "Thesis or chapter", "Other"]),
    ("summary", "Abstract or a short summary", "area", True, None),
    ("rights", "I'm an author, and sharing it here is allowed (open access, a preprint, or the publisher permits it).", "agree", True, None),
    ("safe", "Nothing in it is confidential, commercially sensitive or export-controlled.", "agree", True, None),
]
ARTICLE_FIELDS = [
    ("name", "Name", "text", True, None),
    ("email", "Email", "email", True, None),
    ("role", "Role and department", "text", True, None),
    ("title", "Working title", "text", True, None),
    ("summary", "What it's about, in two or three sentences", "area", True, None),
    ("pics", "Any pictures are mine or used with permission.", "agree", True, None),
    ("safe", "Nothing in it is confidential, commercially sensitive or export-controlled.", "agree", True, None),
    ("publish", "I agree to it being published on this website with my name.", "agree", True, None),
]


def layout(path: str, title: str, body: str, description: str, current: str = "", head_extra="", csp: str = "") -> str:
    csp = csp or CSP
    depth = path.count("/")
    root = "../" * depth
    links = "".join(
        f'<a href="{root}{href}"{" aria-current=\"page\"" if href == current else ""}>{label}</a>'
        for href, label in NAV[1:]
        if not (href == "research.html" and not CFG.get("research_open"))          # hidden while locked
        and not (href == "members.html" and accounts_on()))                        # then it's the gold button
    join_href, join_label = ("members.html", "Join or sign in") if accounts_on() else ("join.html", "Join the network")
    full_title = f"{title} | {CFG['name']}" if title != CFG["name"] else title
    canonical = CFG["base_url"] + ("" if path == "index.html" else path)
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canonical)}">
<meta name="theme-color" content="#121A4A">
<link rel="icon" href="{root}assets/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{root}assets/style.css">
<link rel="alternate" type="application/rss+xml" title="News" href="{root}feed.xml">
{head_extra}</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-head">
  <div class="wrap">
    <a class="lockup" href="{root}index.html" aria-label="{esc(CFG['name'])}: home">{LOGO}<div><b>CHADWICK</b><span>YOUNG NUCLEAR NETWORK</span></div></a>
    <button class="menu-btn" type="button" aria-expanded="false" aria-controls="nav">Menu</button>
    <nav class="nav" id="nav" aria-label="Main">{links}<a class="join" href="{root}{join_href}"{' aria-current="page"' if current == join_href else ""}>{join_label}</a></nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="site-foot">
  <div class="wrap">
    <div><b>{esc(CFG['name'])}</b>
      <p>A student-led network for nuclear researchers at Liverpool, hosted by the {esc(CFG['host'])}.</p></div>
    <div><b>Get involved</b><ul>
      <li><a href="{root}join.html">Join the network</a></li><li><a href="{root}partners.html">Work with us</a></li>
      <li><a href="{root}articles.html#write">Write for us</a></li><li><a href="{CFG['linktree']}"{ext(CFG['linktree'])}>Linktree</a></li></ul></div>
    <div><b>Contact</b><ul>
      <li><a href="mailto:{esc(CFG['email'])}">{esc(CFG['email'])}</a></li>
      <li><a href="{root}privacy.html">Privacy</a></li><li><a href="{root}feed.xml">News feed (RSS)</a></li></ul></div>
    <p class="legal">Events and conferences from other organisations are collected automatically from their public
      listings each week; the details belong to them, so always check the organiser's page before booking.
      Updated {fmt(TODAY, False)}.</p>
  </div>
</footer>
<script src="{root}assets/site.js" defer></script>
</body>
</html>
"""


def page_head(title: str, intro: str = "", crumb: str = "") -> str:
    return (f'<section class="page-head"><div class="wrap">{crumb}<h1>{title}</h1>'
            f'{f"<p>{intro}</p>" if intro else ""}</div></section>')


def write(path: str, html_text: str):
    target = OUT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html_text, encoding="utf-8")


# --------------------------------------------------------------------------- conferences: what field?
FIELDS = [   # checked in this order; the first match wins
    ("Nuclear physics", r"nuclear (structure|physics|data|astro)|exotic|hadron|radioactive beam|nuclei|quark|neutrino"),
    ("Fusion and plasma", r"fusion|plasma|tokamak|stellarator"),
    ("Nuclear medicine and medical physics", r"medic|radiotherap|radiopharm|imaging|theranost|oncolog|clinical|patient|cancer|health|cardiol|ultrasound|optical radiation"),
    ("Radiation protection", r"radiation protection|radiolog|dosim|exposure|emergenc|radiation safety"),
    ("Detectors and instrumentation", r"detector|instrument|sensor|measurement|spectroscop|accelerator"),
    ("Nuclear energy and engineering", r"reactor|power|npp|plant|smr|energy|fuel|decommission|waste|engineering|safety|safeguard|security|transport|material"),
    ("Nuclear applications", r"hydrolog|isotope|agricultur|insect|food|water|environment|industr|tracer"),
]
FIELD_KEYS = {name: re.sub(r"[^a-z]", "", name.lower())[:12] for name, _ in FIELDS}
ORG_FIELD = {"IPEM": "Nuclear medicine and medical physics", "SRP": "Radiation protection"}
CONF_WORDS = re.compile(r"conference|congress|symposium|summer school|school on|workshop|annual meeting|forum", re.I)


CAREERS = re.compile(r"career|\bcv\b|skills|chartership|professional|mentor|network(ing)?\b|jobs?\b|phd|student|early.career|graduate|ygn|leadership", re.I)
EUROPE = set("""albania andorra austria belgium bosnia bulgaria croatia cyprus czech denmark estonia finland france germany greece
hungary iceland ireland italy latvia liechtenstein lithuania luxembourg malta moldova monaco montenegro netherlands norway
poland portugal romania serbia slovakia slovenia spain sweden switzerland ukraine""".split())
N_AMERICA = {"united states", "canada", "mexico"}


def interests_of(text: str, org: str = "") -> list[str]:
    keys = [FIELD_KEYS[name] for name, rx in FIELDS if re.search(rx, text, re.I)]
    if not keys and org.split(" / ")[0] in ORG_FIELD:
        keys = [FIELD_KEYS[ORG_FIELD[org.split(" / ")[0]]]]
    if CAREERS.search(text):
        keys.append("careers")
    return keys


def region_of(country: str, location: str = "") -> str:
    c = (country or "").lower()
    if re.search(r"online|virtual|webinar|teams|zoom", location or "", re.I):
        return "online"
    if c in ("united kingdom", "uk") or not c and not location:
        return "uk"
    if c.split()[0] in EUROPE if c else False:
        return "europe"
    if c in N_AMERICA:
        return "namerica"
    return "world" if c else "uk"


def field_of(title: str, org: str = "") -> str:
    for name, rx in FIELDS:
        if re.search(rx, title, re.I):
            return name
    return ORG_FIELD.get(org.split(" / ")[0], "Nuclear applications")


# --------------------------------------------------------------------------- pages
def own_event_row(e: dict, full: bool) -> str:
    d = date_of(e.get("date"))
    deadline = date_of(e.get("deadline"))
    signup = e.get("signup", "")
    href = f"mailto:{CFG['email']}" if signup == "mailto" else signup
    facts = []
    if d:
        facts.append(("When", f"{fmt(d)}{', ' + esc(e['time']) if e.get('time') else ''}"))
    else:
        facts.append(("When", "Date to be confirmed"))
    for key, label in (("place", "Where"), ("speaker", "Speaker"), ("who", "Who can come")):
        if e.get(key):
            facts.append((label, esc(e[key])))
    if deadline:
        facts.append(("Entries close", fmt(deadline)))
    dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts)
    button = (f'<a class="btn btn-navy" href="{esc(href)}"{ext(href)}>{esc(e.get("signup_label") or "Sign up")}</a>'
              if href else "")
    anchor = e.get("id") or e["slug"]
    body = f'<div class="prose">{markdown(e["body"])}</div>' if full else f'<p class="muted">{inline(e["body"].split(chr(10))[0])}</p>'
    return (f'<article class="feature" id="{esc(anchor)}"><div class="body"><span class="tag">Our event</span>'
            f'<h3>{esc(e["title"])}</h3>{body}<div class="actions">{button}</div></div>'
            f'<div class="side"><dl>{dl}</dl></div></article>')


def ext_row(e: dict, tags: str) -> str:
    s, f = dt.date.fromisoformat(e["start"]), dt.date.fromisoformat(e["end"])
    month = "ongoing" if s < TODAY else s.strftime("%Y-%m")
    chips = "".join(f'<span class="org">{esc(o)}</span>' for o in e["org"].split(" / "))
    loc = f'<span>{esc(e["location"])}</span>' if e.get("location") else ""
    field = f'<span>{esc(e["field"])}</span>' if e.get("field") else ""
    deadline = f'<span>Abstracts by {fmt(date_of(e["deadline"]))}</span>' if date_of(e.get("deadline", "")) else ""
    place = f' data-place="{esc(e["place_key"])}"' if e.get("place_key") else ""
    keys = sorted(set(([FIELD_KEYS[e["field"]]] if e.get("field") in FIELD_KEYS else []) + interests_of(e["title"] + " " + e.get("category", ""), e["org"])))
    place += f' data-fields="{" ".join(keys)}"' if keys else ""
    return (f'<article class="row" data-month="{month}" data-tags="{esc(tags)}"{place}>{date_box(s, f)}<div>'
            f'<h3><a href="{esc(e["url"])}"{ext(e["url"])}>{esc(e["title"])}</a></h3>'
            f'<div class="meta">{chips}<span>{span(s, f)}</span>{loc}{field}{deadline}</div></div></article>')


def grouped(rows: list[tuple[dict, str]]) -> str:
    out, month = [], None
    for e, tags in rows:
        s = dt.date.fromisoformat(e["start"])
        m = "ongoing" if s < TODAY else s.strftime("%Y-%m")
        if m != month:
            out.append(f'<h3 class="month" data-month-head="{m}">{"Running now" if m == "ongoing" else s.strftime("%B %Y")}</h3>')
            month = m
        out.append(ext_row(e, tags))
    return "\n".join(out)


def org_codes(org: str) -> list[str]:
    codes = []
    for part in org.split(" / "):
        codes += {"NI YGN": ["NI", "YGN"], "WiN UK": ["WiN"]}.get(part, [part])
    return codes


ORG_FILTERS = [("NI", "Nuclear Institute"), ("YGN", "YGN"), ("SRP", "SRP"), ("WiN", "WiN UK"),
               ("IPEM", "IPEM"), ("IOP", "IOP"), ("NIA", "NIA")]


def chips(options, label) -> str:
    b = '<button type="button" data-value="all" aria-pressed="true">All</button>'
    b += "".join(f'<button type="button" data-value="{esc(k)}" aria-pressed="false">{esc(v)}</button>' for k, v in options)
    return f'<div class="chips" role="group" aria-label="{label}">{b}</div>'


def build(scraped: list[dict], errors: dict):
    import scrape_events as se

    own = load("events")
    own_up = sorted([e for e in own if (date_of(e.get("date")) or date_of(e.get("deadline")) or TODAY) >= TODAY],
                    key=lambda e: date_of(e.get("date")) or date_of(e.get("deadline")) or dt.date.max)
    own_past = sorted([e for e in own if date_of(e.get("date")) and date_of(e["date"]) < TODAY],
                      key=lambda e: e["date"], reverse=True)
    news = sorted(load("news"), key=lambda n: n.get("date", ""), reverse=True)
    articles = sorted(load("articles"), key=lambda n: n.get("date", ""), reverse=True)
    opps = sorted([o for o in load("opportunities") if (date_of(o.get("closes")) or dt.date.max) >= TODAY],
                  key=lambda o: o.get("closes") or "9999")

    # events (membership groups) and conferences (IAEA, conference-like events, and the committee's list)
    is_conf_org = lambda e: e["org"].split(" / ")[0] in se.CONFERENCE_ORGS
    events = [e for e in scraped if not is_conf_org(e)]
    confs = [dict(e) for e in scraped if is_conf_org(e) or CONF_WORDS.search(e["title"])]
    added = CONTENT / "conferences.csv"
    if added.exists():
        for r in csv.DictReader(added.open(encoding="utf-8-sig")):
            s, f = date_of(r.get("start")), date_of(r.get("end")) or date_of(r.get("start"))
            if s and f and f >= TODAY and r.get("title") and r.get("url"):
                confs.append({"org": r.get("organiser") or "Added by us", "title": r["title"], "start": s.isoformat(),
                              "end": f.isoformat(), "location": r.get("location", ""), "url": r["url"],
                              "field": r.get("field") or "", "deadline": r.get("deadline", "")})
    for c in confs:
        c["field"] = c.get("field") or (ORG_FIELD.get(c["org"]) if c["org"] in ORG_FIELD and not re.search(FIELDS[1][1], c["title"], re.I) else field_of(c["title"], c["org"]))
    confs.sort(key=lambda e: (e["start"], e["title"]))

    # where they are: one dot per place on the world map
    geo = geomap.geocode_all({c["location"] for c in confs if c.get("location")}, se.get)
    points: dict[str, list] = {}
    for c in confs:
        g = geo.get(c.get("location", ""))
        if g:
            c["place_key"] = geomap.place_key(g[2])
            points.setdefault(g[2], [g[0], g[1], 0])[2] += 1
    unmapped = sum(1 for c in confs if not c.get("place_key"))
    series = list(csv.DictReader((CONTENT / "conference_series.csv").open(encoding="utf-8-sig")))

    # ---- home
    own_row = own_event_row(own_up[0], full=False) if own_up else ""
    ext_next = "\n".join(ext_row(e, "") for e in [e for e in events if e["start"] >= TODAY.isoformat()][:5])
    conf_next = "\n".join(ext_row(e, "") for e in [e for e in confs if e["start"] >= TODAY.isoformat()][:4])
    news_cards = "".join(post_card(n, "news") for n in news[:3])
    home = f"""
<section class="hero"><div class="wrap">
  <h1>Nuclear researchers at Liverpool, connected.</h1>
  <p class="lede">A student-led network for PhD students, postdocs and early-career researchers in anything nuclear:
    physics, engineering, chemistry, medicine, policy and beyond. Talks, workshops, site visits and a summer school,
    hosted by the {esc(CFG['host'].split(',')[0])}.</p>
  <div class="actions"><a class="btn btn-gold" href="join.html">Join the network</a><a class="btn btn-line" href="events.html">See what's on</a></div>
</div>{MARK}</section>

<section class="section"><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}Coming up</h2><a href="events.html">All our events</a></div>
  {own_row or '<p class="empty">Our next event will be announced soon. Join the network to hear first.</p>'}
</div></section>

<section class="section foryou-home" data-foryou-home><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}Picked for you</h2><a href="for-you.html">Change what you see</a></div>
  <div class="list" data-suggestions data-limit="5"></div>
  <div class="note" data-foryou-invite><p><strong>Want suggestions?</strong> Tell us what you're into, and the site will
    pick the events, conferences and opportunities most likely to suit you. It's kept only in your browser.</p>
    <div class="actions"><a class="btn btn-navy" href="for-you.html">Choose my interests</a></div></div>
</div></section>

<section class="section"><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}Across the UK</h2><a href="events.html#digest">All {len(events)} events</a></div>
  <p class="lead-in">Talks, webinars and socials from the UK's nuclear membership groups, collected every week.</p>
  <div class="list">{ext_next or '<p class="empty">No upcoming events found this week.</p>'}</div>
</div></section>

<section class="section"><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}Conferences</h2><a href="conferences.html">All {len(confs)} conferences</a></div>
  <div class="list">{conf_next or '<p class="empty">No upcoming conferences found this week.</p>'}</div>
</div></section>

<section class="section"><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}News</h2><a href="news.html">All news</a></div>
  <div class="posts">{news_cards or '<p class="empty">No news yet.</p>'}</div>
</div></section>

<section class="band"><div class="wrap">
  <div><h2>Could you give one talk?</h2>
    <p>Our members work across radiation detection and protection, fusion, reactor physics, materials,
      decommissioning, nuclear medicine and policy, and they'd love to hear from you. A single talk, a visit or a
      shared opportunity all help, with no commitment beyond that.</p></div>
  <div class="actions"><a class="btn btn-navy" href="partners.html">Work with us</a></div>
</div></section>
"""
    write("index.html", layout("index.html", CFG["name"], home, CFG["tagline"] + " A student-led network hosted by the Chadwick Institute for Nuclear Innovation."))

    # ---- events
    present = {c for e in events for c in org_codes(e["org"])}
    rows = [(e, " ".join(org_codes(e["org"]))) for e in events]
    also = "".join(f'<li><a href="{esc(u)}"{ext(u)}>{esc(n)}</a></li>' for n, u in se.MANUAL)
    past = "".join(f'<li>{fmt(date_of(e["date"]))}: {esc(e["title"])}</li>' for e in own_past)
    ev = page_head("Events", "Our own talks and workshops, and what's on across the UK's nuclear membership groups.")
    ev += f"""
<section class="section"><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}Our events</h2></div>
  <div class="list" data-gap>{''.join(own_event_row(e, True) for e in own_up) or '<p class="empty">Our next event will be announced soon.</p>'}</div>
  {f'<details class="small"><summary>Past events</summary><ul>{past}</ul></details>' if past else ''}
</div></section>
<section class="section" id="digest"><div class="wrap" data-filter-list>
  <div class="sec-head"><h2>{TRAIL}Across the UK</h2></div>
  <p class="lead-in">Collected every Monday from the groups' own public listings. Follow each link for details and booking.</p>
  <div class="tools">{chips([(k, v) for k, v in ORG_FILTERS if k in present], "Filter by organisation")}
    <label class="search"><span class="small muted">Search</span><input type="search" data-search placeholder="Title or place"></label></div>
  <p class="count"><span data-shown>{len(events)}</span> events</p>
  {grouped(rows)}
  <p class="empty hidden" data-none>No events match. Try another organisation or clear the search.</p>
  <div class="note"><p><strong>Also worth checking.</strong> These groups' events can't be collected automatically:</p><ul>{also}</ul></div>
</div></section>"""
    write("events.html", layout("events.html", "Events", ev, "Our own events, and upcoming talks, webinars and socials from UK nuclear membership groups.", "events.html"))

    # ---- conferences
    present_f = [f for f, _ in FIELDS if any(c["field"] == f for c in confs)]
    crow = [(c, FIELD_KEYS.get(c["field"], "other")) for c in confs]
    by_field: dict[str, list] = {}
    for s in series:
        by_field.setdefault(s["field"], []).append(s)
    directory = "".join(
        f'<section><h3>{esc(f)}</h3><ul>' + "".join(
            f'<li><a href="{esc(s["url"])}"{ext(s["url"])}>{esc(s["name"])}</a><span>{esc(s["organiser"])}. {esc(s["what"])}</span></li>'
            for s in items) + "</ul></section>" for f, items in by_field.items())
    cf = page_head("Conferences", "Upcoming conferences, symposia and schools across nuclear physics, medicine, radiation "
                   "protection, fusion and energy, and a directory of the major conference series in each field.")
    cf += f"""
<section class="section"><div class="wrap" data-filter-list>
  <div class="sec-head"><h2>{TRAIL}Upcoming</h2></div>
  <p class="lead-in">From the IAEA, the American Nuclear Society, the IEEE Nuclear and Plasma Sciences Society, the
    European Physical Society, the UK groups' listings, and conferences our committee adds. IAEA technical meetings,
    which need a nomination, are left out.</p>
  <figure class="map">{geomap.map_svg(points)}
    <figcaption class="small muted">{sum(v[2] for v in points.values())} conferences in {len(points)} places. Select a dot to
      see what's on there.{f" {unmapped} more are online or haven't named a place yet." if unmapped else ""}
      Scroll, pinch or use the buttons to zoom; drag to move around. Map: Natural Earth. Places: GeoNames, via
      Open-Meteo (CC BY 4.0).{" Facilities: Wikidata (CC0) and our own list; select one to read about it." if geomap.load_facilities() else ""}</figcaption>
    {geomap.facilities_legend()}</figure>
  <div class="tools">{chips([(FIELD_KEYS.get(f, 'other'), f) for f in present_f], "Filter by field")}
    <label class="search"><span class="small muted">Search</span><input type="search" data-search placeholder="Title, place or organiser"></label></div>
  <p class="place-note hidden" id="map-list" data-place-note>Showing conferences in <strong data-place-name></strong>.
    <button type="button" class="link-btn" data-place-clear>Show every place</button></p>
  <p class="count"><span data-shown>{len(confs)}</span> conferences</p>
  {grouped(crow)}
  <p class="empty hidden" data-none>Nothing matches. Try another field or clear the search.</p>
</div></section>
<section class="section"><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}Conference series by field</h2></div>
  <p class="lead-in">The main recurring meetings, with a link to each organiser. Dates and calls for abstracts are on their sites.</p>
  <div class="series">{directory}</div>
  <div class="note"><p>Know a conference we've missed, or presenting at one? Tell us and we'll add it.</p>{email_block()}</div>
</div></section>"""
    write("conferences.html", layout("conferences.html", "Conferences", cf, "Upcoming nuclear conferences, symposia and schools by field, and the major conference series.", "conferences.html"))

    # ---- news and articles
    def listing(kind, items, title, intro, empty, extra=""):
        cards = "".join(post_card(i, kind) for i in items)
        body = page_head(title, intro) + f'<section class="section"><div class="wrap"><div class="posts">{cards or f"<p class=empty>{empty}</p>"}</div></div></section>{extra}'
        write(f"{kind}.html", layout(f"{kind}.html", title, body, intro, f"{kind}.html"))
        for i in items:
            d = date_of(i.get("date"))
            by = f'<p class="byline">By {esc(i["author"])}{", " + esc(i["role"]) if i.get("role") else ""}</p>' if i.get("author") else ""
            crumb = f'<a class="crumb" href="../{kind}.html">{title}</a>'
            head = page_head(esc(i["title"]), f'{fmt(d, False) if d else ""}', crumb)
            post = f'{head}<div class="wrap article">{by}<div class="prose">{markdown(i["body"])}</div><p><a href="../{kind}.html">Back to {title.lower()}</a></p></div>'
            write(f"{kind}/{i['slug']}.html", layout(f"{kind}/{i['slug']}.html", i["title"], post, i.get("summary", i["title"]), f"{kind}.html"))

    listing("news", news, "News", "What the network is doing, and nuclear news that matters to early-career researchers.", "No news yet.")
    write_for_us = f"""
<section class="form-band" id="write"><div class="wrap">
  <div class="form-intro"><h2>Write for us</h2>
    <p>Members can write about their research, a conference or site visit, a placement, or a career path. Aim for
      600 to 1,200 words in plain language, with a picture or two if you have them. The committee reads every piece
      before it goes up and will agree any edits with you.</p></div>
  {mail_form("article", "Article for the website", "Working title", ARTICLE_FIELDS, "Write the email",
             "When your email app opens, attach the article (Word or PDF) and any pictures before you send it.")}
</div></section>"""
    listing("articles", articles, "Articles", "Writing by our members: their research, visits, placements and careers.",
            "No articles yet. Be the first: see how to write for us below.", write_for_us)

    # ---- opportunities
    orows = "".join(
        f'<article class="row" data-tags="all">{date_box(date_of(o.get("closes")))}<div>'
        f'<h3><a href="{esc(o.get("url", ""))}"{ext(o.get("url", ""))}>{esc(o["title"])}</a></h3>'
        f'<div class="meta"><span class="org">{esc(o.get("type", "Opportunity"))}</span><span>{esc(o.get("organisation", ""))}</span>'
        f'{f"<span>Closes {fmt(date_of(o["closes"]))}</span>" if date_of(o.get("closes")) else ""}</div>'
        f'<p class="muted small">{inline(o["body"])}</p></div></article>' for o in opps)
    op = page_head("Opportunities", "PhDs, jobs, placements and bursaries we think our members should hear about. Each one comes off the list after it closes.")
    op += f"""<section class="section"><div class="wrap"><div class="list">{orows or '<p class="empty">Nothing open right now. Check back soon, or join the network to get them by email.</p>'}</div>
  <div class="note"><p>Have an opportunity for nuclear PGRs and postdocs? Send us the details and a link.</p>{email_block()}</div></div></section>"""
    write("opportunities.html", layout("opportunities.html", "Opportunities", op, "PhDs, jobs, placements and bursaries for nuclear researchers.", "opportunities.html"))

    # ---- join
    jn = page_head("Join the network", "Free, and open to anyone at the University of Liverpool with an interest in nuclear science and technology, whatever their department.")
    jn += f"""
<section class="section"><div class="wrap cols">
  <div><h2>{TRAIL}Who it's for</h2>
    <p>Mainly PhD, MPhil and MRes students and postdocs, including the RAPTOR and SATURN-2 doctoral cohorts.
      Undergraduates and MSc students are welcome at most events, and some events are open to early-career
      professionals in industry.</p></div>
  <div><h2>{TRAIL}What you get</h2>
    <ul class="checks"><li>Talks from industry and academic speakers on fission, fusion, decommissioning, radiation
      protection, nuclear medicine, policy and careers</li><li>Practical workshops, from detectors to Monte Carlo
      modelling and routes to chartership</li><li>Site visits and industry evenings with employers in the North West</li>
      <li>A place to try out your research on people from other departments</li><li>Our summer school, events digest and
      opportunities by email</li></ul></div>
</div></section>
<section class="form-band" id="signup"><div class="wrap">
  <div class="form-intro"><h2>Sign up</h2><p>It takes under a minute. We use your details only to tell you about the
    network's events and opportunities; they stay with the committee and are never shared with partners. You can leave
    at any time. See our <a href="privacy.html">privacy notice</a>.</p></div>
  {mail_form("join", "Join the network", "Full name", JOIN_FIELDS, "Write my sign-up email")}
</div></section>
<section class="section"><div class="wrap"><div class="prose"><p>Questions first?</p>{email_block()}</div></div></section>"""
    write("join.html", layout("join.html", "Join the network", jn, "Join the Chadwick Institute Young Nuclear Network: free for nuclear researchers at Liverpool.", "join.html"))

    # ---- partners: flexible, one-off help is as welcome as anything longer
    ways = [
        ("Give a talk", "One talk, once. Your work, your career, or where your field is going; 30 to 60 minutes, in person or online."),
        ("Run a workshop or careers session", "A hands-on session, a CV clinic, or an honest look at what working in your organisation is like."),
        ("Host a visit", "Show a small group around your site, lab or office. We'll handle names for security checks well ahead."),
        ("Share an opportunity", "Placements, internships, jobs, PhDs or events. Send them over and we'll pass them on."),
        ("Mentor someone", "An occasional conversation with a PhD student or postdoc thinking about their next step."),
        ("Support an event", "Refreshments, a prize for a student talk, or help with a student's travel. Small things make a big difference."),
        ("Help with the summer school", "Teach a session, lend kit, or support a place for a student who couldn't otherwise come."),
    ]
    way_list = "".join(f"<li><strong>{esc(t)}</strong><span>{esc(d)}</span></li>" for t, d in ways)
    pt = page_head("Work with us", "Whether you can give one talk or would like to do more over time, we'd love to hear from you. "
                   "There's no fee, no minimum and no yearly commitment: just whatever suits you.")
    pt += f"""
<section class="section"><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}Ways to help</h2></div>
  <p class="lead-in">Do as much or as little as you like. Most people start with a single talk, and that alone means a lot to
    our members.</p>
  <ul class="ways">{way_list}</ul>
</div></section>
<section class="section"><div class="wrap cols">
  <div><h2>{TRAIL}How it works</h2><ol class="steps">
    <li><span>Tell us what you have in mind, using the form below or by email. A rough idea is plenty.</span></li>
    <li><span>We'll get back to you within a week to find a date and format that suit you.</span></li>
    <li><span>We look after the room, the audience and the publicity. You just turn up, or join online.</span></li>
    <li><span>Afterwards we'll let you know how it went, and say thank you properly.</span></li></ol>
    <p class="small muted">If you'd like to give money or equipment, it goes through the Chadwick Institute at the University of
      Liverpool so it is handled properly, and we'll agree in a short note what it's for.</p></div>
  <div><h2>{TRAIL}What we'll do in return</h2><ul class="checks">
    <li>Thank you publicly, on this website and LinkedIn, if you'd like us to.</li>
    <li>Introduce you to members working in your area.</li>
    <li>Share your opportunities with people who are looking for them.</li>
    <li>Keep members' personal details private: we never pass them on.</li>
    <li>Stay independent: support never buys influence over research, teaching or what the network says, and we're open about who helps us.</li></ul></div>
</div></section>
<section class="form-band" id="register"><div class="wrap">
  <div class="form-intro"><h2>Get in touch</h2><p>Tell us a little about yourself and what you'd like to do. Tick as many
    or as few as you like; we'll reply within a week.</p></div>
  {mail_form("partner", "Getting involved", "Organisation", PARTNER_FIELDS, "Write the email")}
</div></section>"""
    write("partners.html", layout("partners.html", "Work with us", pt, "Give a one-off talk, host a visit or help in another way: work with the Chadwick Institute Young Nuclear Network.", "partners.html"))

    # ---- about
    ab = page_head("About the network", f"{esc(CFG['tagline'])}")
    ab += f"""
<section class="section"><div class="wrap cols">
  <div class="prose"><h2>{TRAIL}Who we are</h2>
    <p>Nuclear researchers at Liverpool sit across Physics, Engineering, Chemistry, Environmental Sciences, Medicine and
      beyond, yet rarely meet. The Chadwick Institute Young Nuclear Network brings them together: a student-led
      community of PGRs and postdocs, hosted by the Chadwick Institute for Nuclear Innovation.</p>
    <p>The Institute, launched in June 2026, is named after Sir James Chadwick, who discovered the neutron and held the
      Chair of Physics at Liverpool.</p></div>
  <div class="prose"><h2>{TRAIL}What we aim to do</h2><ul class="checks">
    <li><strong>Community.</strong> A cross-disciplinary community of nuclear researchers at Liverpool.</li>
    <li><strong>Industry.</strong> Lasting relationships with employers, starting with the North West nuclear cluster.</li>
    <li><strong>Professional development.</strong> Support towards membership of professional bodies, CPD and, in time, chartership.</li>
    <li><strong>Skills.</strong> Practical, employer-relevant training, starting with an annual summer school.</li>
    <li><strong>Visibility.</strong> A higher profile for Liverpool's nuclear research, regionally and nationally.</li>
    <li><strong>Outreach.</strong> Public engagement and schools outreach on nuclear science and radiation.</li></ul></div>
</div></section>
{committee_section()}
<section class="section"><div class="wrap cols">
  <div class="prose"><h2>{TRAIL}How we're run</h2>
    <p>The student committee above runs the network and makes its decisions. Prof Peter Bryant, Director of the Chadwick
      Institute, is our academic adviser.</p></div>
  <div class="prose"><h2>{TRAIL}Who we work with</h2>
    <p>The Nuclear Institute and its Young Generation Network, the Society for Radiological Protection, the British
      Nuclear Medicine Society, the UK Fusion Student Network and employers across the North West nuclear cluster.</p></div>
</div></section>
<section class="section"><div class="wrap"><div class="prose"><h2>{TRAIL}Contact</h2>{email_block()}
  <p><a href="{CFG['linktree']}"{ext(CFG['linktree'])}>Instagram, LinkedIn and more on our Linktree</a></p></div></div></section>"""
    write("about.html", layout("about.html", "About", ab, "About the Chadwick Institute Young Nuclear Network: who we are, what we do and who we work with.", "about.html"))

    # ---- research: members' papers and reports. Locked (no entries or files published) until research_open is true
    research = sorted(load("research"), key=lambda r: r.get("date", ""), reverse=True)
    is_open = bool(CFG.get("research_open"))
    share = f"""
<section class="form-band" id="share"><div class="wrap">
  <div class="form-intro"><h2>Share your paper</h2><p>Members can share a paper, preprint, report or thesis chapter. Send us
    the details and a link (a DOI or arXiv link is best); if it isn't published anywhere, attach the file to the email.
    The committee checks each one before it goes up.</p></div>
  {mail_form("paper", "Paper for the research page", "Title", PAPER_FIELDS, "Write the email",
             "If you're sending a file, attach it in your email app before you send.")}
</div></section>"""
    if is_open:
        rows = []
        for r in research:
            f = r.get("file", "")
            src = (HERE / f).resolve() if f and not f.startswith("http") else None
            if src and src.exists():
                (OUT / "research").mkdir(exist_ok=True)
                shutil.copy2(src, OUT / "research" / src.name)
                link = f"research/{src.name}"
            else:
                link = r.get("link") or f
            rows.append(f'''<article class="paper"><span class="tag">{esc(r.get("kind", "Paper"))}</span>
  <h3><a href="{esc(link)}"{ext(link)}>{esc(r["title"])}</a></h3>
  <p class="byline">{esc(r.get("authors", ""))}{", " + fmt(date_of(r["date"]), False) if date_of(r.get("date")) else ""}</p>
  <p class="muted">{inline(r.get("summary", ""))}</p>
  <details><summary>Abstract</summary><div class="prose">{markdown(r["body"])}</div></details></article>''')
        rs = page_head("Research", "Papers, reports and projects by members of the network.")
        rs += f'<section class="section"><div class="wrap"><div class="papers">{"".join(rows) or "<p class=empty>Nothing here yet.</p>"}</div></div></section>{share}'
    else:
        rs = page_head("Research", "Papers, reports and projects by members of the network.")
        rs += f"""<section class="section"><div class="wrap"><div class="locked">
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 10V7a5 5 0 0 1 10 0v3h1a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h1Zm2 0h6V7a3 3 0 0 0-6 0v3Z"/></svg>
  <div><h2>Opening soon</h2><p>We're getting this section ready. When it opens it will hold papers, reports and project
    write-ups by our members, starting with the network's own research on the Chadwick Institute and the North West
    nuclear sector. Join the network to hear when it opens.</p>
  <div class="actions"><a class="btn btn-navy" href="join.html">Join the network</a></div></div>
</div></div></section>"""
    write("research.html", layout("research.html", "Research", rs, "Papers, reports and projects by members of the Chadwick Institute Young Nuclear Network.", "research.html"))

    # ---- members' area (Supabase). Without supabase_url and supabase_anon_key in site.json it says it opens soon.
    write("members.html", members_page())

    # ---- privacy and 404
    pv = page_head("Privacy")
    pv += f"""<section class="section"><div class="wrap"><div class="prose">
  <h2>This website</h2>
  <p>This website does not use cookies, analytics or tracking of any kind, and it does not collect any personal data.
    It is hosted on GitHub Pages, which keeps standard server logs (such as IP addresses) for security; see GitHub's
    privacy statement. Fonts are loaded from Google Fonts.</p>
  <h2>Suggestions "for you"</h2>
  <p>If you choose interests on the <a href="for-you.html">For you</a> page, they are saved in your own browser (its local
    storage), on that device only, so the site can show suggestions. If you also tick "learn from what I open", the
    browser counts which subjects you open, again only on your device. None of it is sent to us or anyone else, and
    "Forget me" deletes it. If you never use the page, nothing is stored.</p>
  <h2 id="members">Member accounts</h2>
  <p>If you create a free account, your account and profile are stored with Supabase, in its London data centre, on the
    network's behalf. Supabase checks your password and keeps only a secure (salted, hashed) version of it; nobody,
    including the committee, can see your password. Your name, username and email are needed to run your account;
    everything else in your profile is optional, and each field says what it's used for. Dietary and access needs are
    kept only if you tick the box that allows it. Other members see you in the directory only if you choose to be listed,
    and then only the details listed there. The committee can see member profiles in order to run the network, and never
    shares them with partners or anyone else. You can download your data or delete your account at any time from the
    Account tab; deleting it removes your profile straight away. Accounts unused for three years are deleted.</p>
  <h2>Signing up</h2>
  <p>The forms on this website don't send or store anything themselves: pressing the button opens your own
    email app with a message to the network's mailbox, and nothing reaches us until you send it. We ask only for what
    we need to run the network: your name, email, department and interests (or, if you'd like to work with us, your organisation and
    contact details). Your details are seen only by the student committee, used only to tell you about the network's events
    and opportunities, and never shared with partners or anyone else. We follow the University of Liverpool's data
    protection policy.</p>
  <h2>Leaving or asking about your data</h2>
  <p>Every email we send has an unsubscribe link. To see, correct or delete what we hold about you, email us and we'll
    do it within a month.</p>{email_block()}
  <h2>Other organisations' events</h2>
  <p>Event and conference listings are collected from other organisations' public pages. We keep only the title, dates,
    place, organiser and a link; descriptions and images stay on their sites.</p>
</div></div></section>"""
    write("privacy.html", layout("privacy.html", "Privacy", pv, "How the Chadwick Institute Young Nuclear Network handles personal data."))
    nf = page_head("Page not found", 'That page has moved or never existed. Try the <a href="index.html">home page</a> or our <a href="events.html">events</a>.')
    write("404.html", layout("404.html", "Page not found", nf, "Page not found."))

    # ---- items.json: what the "For you" suggestions choose from (read only by the visitor's own browser)
    items = []
    for e in own_up:
        d = date_of(e.get("date")) or date_of(e.get("deadline"))
        items.append({"kind": "ours", "title": e["title"], "url": f"events.html#{e.get('id') or e['slug']}",
                      "start": d.isoformat() if d else "", "org": "Us", "region": "uk",
                      "fields": interests_of(e["title"] + " " + e["body"][:400]) + ["ours"]})
    for e in events:
        items.append({"kind": "event", "title": e["title"], "url": e["url"], "start": e["start"], "org": e["org"],
                      "region": region_of("", e.get("location", "") + " " + e.get("category", "")),
                      "fields": interests_of(e["title"] + " " + e.get("category", ""), e["org"])})
    for c in confs:
        g = geo.get(c.get("location", "")) if c.get("location") else None
        items.append({"kind": "conference", "title": c["title"], "url": c["url"], "start": c["start"], "org": c["org"],
                      "place": g[2] if g else c.get("location", ""),
                      "region": region_of(g[2].split(", ")[-1] if g else "", c.get("location", "")) if (g or c.get("location")) else "world",
                      "fields": sorted(set([FIELD_KEYS.get(c["field"], "")] + interests_of(c["title"], c["org"])) - {""})})
    for o in opps:
        items.append({"kind": "opportunity", "title": o["title"], "url": "opportunities.html", "start": o.get("closes", ""),
                      "org": o.get("organisation", ""), "region": "uk",
                      "fields": sorted(set(interests_of(o["title"] + " " + o["body"]) + ["careers"]))})
    for n in news[:12]:
        items.append({"kind": "news", "title": n["title"], "url": f"news/{n['slug']}.html", "start": n.get("date", ""),
                      "org": "News", "region": "uk", "fields": interests_of(n["title"] + " " + n.get("summary", "") + " " + n["body"][:600])})
    seen, unique = set(), []                     # an IOP conference is both an event and a conference: keep one
    for it in sorted(items, key=lambda i: i["kind"] != "conference"):
        k = (re.sub(r"\W", "", it["title"].lower()), it["start"])
        if k not in seen:
            seen.add(k)
            unique.append(it)
    items = unique
    (OUT / "items.json").write_text(json.dumps({"built": TODAY.isoformat(), "fields": {FIELD_KEYS[f]: f for f, _ in FIELDS} | {"careers": "Careers and skills"},
                                                "items": items}, ensure_ascii=False), encoding="utf-8")

    # ---- For you: the visitor tells us (or lets the site learn) what they're into; all of it stays in their browser
    field_boxes = "".join(f'<label><input type="checkbox" name="interest" value="{FIELD_KEYS[f]}"> {esc(f)}</label>' for f, _ in FIELDS)
    field_boxes += '<label><input type="checkbox" name="interest" value="careers"> Careers and skills</label>'
    fy = page_head("For you", "Tell us what you're into and we'll pick the events, conferences and opportunities most likely to suit you. "
                   "Your choices are kept only in this browser, on this device: we never see them.")
    fy += f"""
<section class="section"><div class="wrap foryou" data-foryou-page>
  <form class="mailform prefs" data-prefs>
    <fieldset class="field"><legend>I'm interested in</legend><div class="boxes">{field_boxes}</div></fieldset>
    <div class="grid">
      <label class="field"><span>I am</span><select name="role"><option value="">Rather not say</option>
        <option value="undergrad">An undergraduate or MSc student</option><option value="pgr">A PhD student</option>
        <option value="postdoc">A postdoc or researcher</option><option value="industry">Working in industry</option>
        <option value="staff">University staff</option></select></label>
      <label class="field"><span>I'd travel to</span><select name="travel"><option value="anywhere">Anywhere</option>
        <option value="europe">The UK and Europe</option><option value="uk">The UK only</option><option value="online">Online only</option></select></label>
    </div>
    <label class="agree wide"><input type="checkbox" name="learn"> <span>Learn from what I open: a small model in this
      browser notices which events I pick and suggests ones like them (it never leaves this device)</span></label>
    <div class="actions"><button class="btn btn-navy" type="submit">Save and show my suggestions</button>
      <button class="btn btn-line" type="button" data-forget>Forget me</button></div>
    <p class="small muted hidden" role="status" data-saved>Saved in this browser.</p>
  </form>
  <div class="sec-head"><h2>{TRAIL}Suggested for you</h2></div>
  <div class="list" data-suggestions data-limit="20"><p class="empty">Choose a few interests above and we'll suggest things here.</p></div>
  <p class="learned" data-learned></p>
  <p class="small muted">How it works: each suggestion matches your interests, is somewhere you'd go, and is coming up soon.
    Nothing is sent anywhere; "Forget me" deletes it all.</p>
</div></section>"""
    write("for-you.html", layout("for-you.html", "For you", fy, "Suggestions picked for your interests, kept only in your browser.", "for-you.html"))

    # ---- feeds and data
    items = "".join(
        f"<item><title>{esc(n['title'])}</title><link>{CFG['base_url']}news/{n['slug']}.html</link>"
        f"<guid>{CFG['base_url']}news/{n['slug']}.html</guid><description>{esc(n.get('summary', ''))}</description>"
        f"<pubDate>{dt.datetime.combine(date_of(n['date']) or TODAY, dt.time(9)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>"
        for n in news[:20])
    (OUT / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{esc(CFG["name"])}: news</title>'
        f'<link>{CFG["base_url"]}</link><description>{esc(CFG["tagline"])}</description>{items}</channel></rss>', encoding="utf-8")
    pages = [p.relative_to(OUT).as_posix() for p in OUT.rglob("*.html") if p.name != "404.html"]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
        "".join(f"<url><loc>{CFG['base_url']}{'' if p == 'index.html' else p}</loc></url>" for p in sorted(pages)) +
        "</urlset>", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {CFG['base_url']}sitemap.xml\n", encoding="utf-8")

    print(f"Built {len(pages) + 1} pages: {len(own_up)} of our events, {len(events)} UK events, {len(confs)} conferences, "
          f"{len(news)} news, {len(articles)} articles, {len(opps)} opportunities -> {OUT}")
    if errors:
        print("Sources with errors (their items are missing this week):", ", ".join(errors))


SUPABASE_JS = ("https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js",
               "sha384-0w2KAL2YHP6wKOkUDzkCDGgVvfmHnj02DHeQ6XcHOgTfFsGyonKOpShMH1x6nk9o")


def members_page() -> str:
    url, key = CFG.get("supabase_url", "").rstrip("/"), CFG.get("supabase_anon_key", "")
    head = page_head("Members", "Free membership: your profile, suggestions picked for you, member exclusives and the members' directory.")
    if not (url.startswith("https://") and key):
        body = head + """<section class="section"><div class="wrap"><div class="locked">
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 10V7a5 5 0 0 1 10 0v3h1a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1h1Zm2 0h6V7a3 3 0 0 0-6 0v3Z"/></svg>
  <div><h2>Member accounts are coming soon</h2><p>Soon you'll be able to create a free account, keep your profile and choices,
    and see member exclusives. Until then, you can still pick your interests on the <a href="for-you.html">For you</a> page
    (kept in your browser) and join our mailing list.</p>
  <div class="actions"><a class="btn btn-navy" href="join.html">Join the mailing list</a><a class="btn btn-line" href="for-you.html">For you</a></div></div>
</div></div></section>"""
        return layout("members.html", "Members", body, "The members' area of the Chadwick Institute Young Nuclear Network.", "members.html")

    def boxes(name, options):
        return "".join(f'<label><input type="checkbox" name="{name}" value="{esc(v)}" data-list> {esc(l)}</label>' for v, l in options)
    interests = [(FIELD_KEYS[f], f) for f, _ in FIELDS] + [("careers", "Careers and skills")]
    bodies = [(b, b) for b in ["Nuclear Institute", "Society for Radiological Protection", "Institute of Physics",
                               "IPEM", "British Nuclear Medicine Society", "Women in Nuclear UK", "Other"]]
    updates = [("events", "Our events"), ("digest", "The weekly events digest"), ("conferences", "Conferences and calls for abstracts"),
               ("opportunities", "PhDs, jobs and placements"), ("news", "News")]
    def field(name, label, purpose, kind="text", attrs="", options=None, wide=False):
        cls = "field wide" if wide else "field"
        if kind == "select":
            opts = '<option value="">Rather not say</option>' + "".join(f'<option value="{v}">{esc(l)}</option>' for v, l in options)
            ctl = f'<select name="{name}" {attrs}>{opts}</select>'
        elif kind == "area":
            ctl = f'<textarea name="{name}" rows="3" {attrs}></textarea>'
        else:
            ctl = f'<input name="{name}" type="{kind}" {attrs}>'
        return f'<label class="{cls}"><span>{esc(label)}</span>{ctl}<small class="why-field">{esc(purpose)}</small></label>'

    STATUS = [("undergraduate", "Undergraduate"), ("msc", "MSc student"), ("pgr", "PhD, MPhil or MRes student"), ("postdoc", "Postdoc or researcher"),
              ("staff", "University staff"), ("industry", "Working in industry"), ("other", "Other")]
    profile_form = f"""<form class="mailform member-form" data-profile novalidate>
  <h3>About you</h3><div class="grid">
    {field("full_name", "Full name", "Shown on your account and, if you choose, in the directory.", attrs='maxlength="120" autocomplete="name" required')}
    {field("username", "Username", "Fixed once chosen.", attrs='disabled')}
    {field("pronouns", "Pronouns (optional)", "So we get them right.", attrs='maxlength="30"')}
  </div>
  <h3>Study and work</h3><div class="grid">
    {field("status", "I am", "So we can suggest events at the right level.", "select", options=STATUS)}
    {field("department", "Department", "So we know which departments we reach.", attrs='maxlength="120"')}
    {field("organisation", "Organisation, if not the University", "For members from industry and elsewhere.", attrs='maxlength="120" autocomplete="organization"')}
    {field("year_of_study", "Year of study", "For year-specific events, such as first-year PhD sessions.", attrs='maxlength="30"')}
    {field("group_or_supervisor", "Research group or supervisor", "So we can connect people in related groups.", attrs='maxlength="120"')}
    {field("expected_finish", "Expected to finish", "So we can share jobs and fellowships at the right time.", attrs='maxlength="30" placeholder="e.g. September 2029"')}
  </div>
  <h3>Research and interests</h3><div class="grid">
    {field("research_area", "Research area", "To suggest talks and connect you with people working on similar things.", attrs='maxlength="200"', wide=True)}
    {field("bio", "A short bio", "Shown in the directory if you choose to be listed.", "area", attrs='maxlength="1200"', wide=True)}
  </div>
  <fieldset class="field"><legend>I'm interested in</legend><div class="boxes">{boxes("interests", interests)}</div>
    <small class="why-field">These choose your suggestions on this site.</small></fieldset>
  <div class="grid">
    {field("travel", "I'd travel to", "Suggestions only include places you'd go.", "select", options=[("anywhere", "Anywhere"), ("europe", "The UK and Europe"), ("uk", "The UK only"), ("online", "Online only")])}
    {field("orcid", "ORCID iD", "To link your publications.", attrs='pattern="\\d{{4}}-\\d{{4}}-\\d{{4}}-\\d{{3}}[\\dX]" placeholder="0000-0000-0000-0000"')}
    {field("linkedin", "LinkedIn profile", "Shown in the directory if you choose to be listed.", "url", attrs='placeholder="https://www.linkedin.com/in/..."')}
    {field("website", "Website", "Your group or personal page.", "url", attrs='placeholder="https://..."')}
  </div>
  <label class="agree wide"><input type="checkbox" name="learn_toggle"> <span>Learn from what I open on this site to improve my
    suggestions (the model runs in your browser and is saved to your account)</span></label>
  <h3>Mentoring and skills</h3><div class="grid">
    {field("skills", "Skills and expertise", "Separate with commas. For mentoring and for finding speakers.", attrs='data-csv placeholder="e.g. Geant4, gamma spectroscopy, Python"', wide=True)}
    {field("mentoring", "Mentoring", "For our mentor matching scheme.", "select", options=[("none", "Not for now"), ("want", "I'd like a mentor"), ("offer", "I'm happy to mentor someone"), ("both", "Both")])}
    {field("career_goals", "Career goals", "So we can suggest the right opportunities and mentors.", "area", attrs='maxlength="800"', wide=True)}
  </div>
  <fieldset class="field"><legend>Professional bodies I belong to</legend><div class="boxes">{boxes("professional_bodies", bodies)}</div>
    <small class="why-field">So we know which partnerships matter to members.</small></fieldset>
  <h3>Events and emails</h3>
  <fieldset class="field"><legend>Email me about</legend><div class="boxes">{boxes("email_updates", updates)}</div>
    <small class="why-field">You can change this at any time.</small></fieldset>
  <div class="grid">{field("heard_about_us", "How did you hear about us?", "So we know which publicity works.", attrs='maxlength="120"')}</div>
  <label class="agree wide"><input type="checkbox" name="needs_consent"> <span>I'm happy for the committee to keep my dietary and
    access needs, to plan events. (This can reveal health or beliefs, so we only keep it with your say-so, and delete it if you untick this.)</span></label>
  <div class="grid">
    {field("dietary", "Dietary needs", "For catering at events.", attrs='maxlength="300" data-needs')}
    {field("accessibility", "Access needs", "So every event works for you.", attrs='maxlength="500" data-needs')}
  </div>
  <h3>Directory</h3>
  <label class="agree wide"><input type="checkbox" name="in_directory"> <span>List me in the members' directory, so other
    members can see my name, pronouns, status, department, research area, skills, mentoring choice, LinkedIn and ORCID.</span></label>
  <div class="actions"><button class="btn btn-navy" type="submit">Save my profile</button></div>
  <p class="form-msg hidden" role="status" data-msg></p>
</form>"""

    body = head + f"""
<section class="section"><div class="wrap members" data-members data-url="{esc(url)}" data-key="{esc(key)}">
  <div data-state="out">
    <p class="form-msg hidden" role="status" data-out-msg></p>
    <div class="tabs" role="tablist" data-tabs>
      <button type="button" role="tab" data-tab="signin" aria-selected="true">Sign in</button>
      <button type="button" role="tab" data-tab="create" aria-selected="false">Create a free account</button>
    </div>
    <form class="mailform auth" data-panel="signin" data-signin novalidate>
      <label class="field"><span>Email</span><input name="email" type="email" autocomplete="email" required></label>
      <label class="field"><span>Password</span><input name="password" type="password" autocomplete="current-password" required></label>
      <div class="actions"><button class="btn btn-navy" type="submit">Sign in</button>
        <button class="link-btn" type="button" data-forgot>Forgotten your password?</button></div>
      <p class="form-msg hidden" role="status" data-msg></p>
    </form>
    <form class="mailform auth hidden" data-panel="create" data-create novalidate>
      <p>Membership is free. Once your account exists you can fill in as much or as little of your profile as you like.</p>
      <label class="field"><span>Full name</span><input name="full_name" maxlength="120" autocomplete="name" required></label>
      <label class="field"><span>Username</span><input name="username" maxlength="30" autocomplete="username" required>
        <small class="why-field" data-username-msg>3 to 30 letters, numbers, dots, dashes or underscores. Fixed once chosen.</small></label>
      <label class="field"><span>Email</span><input name="email" type="email" autocomplete="email" required>
        <small class="why-field">You sign in with this. We'll send a link to confirm it.</small></label>
      <label class="field"><span>Password</span><input name="password" type="password" minlength="10" autocomplete="new-password" required>
        <small class="why-field">At least 10 characters. A few random words works well.</small></label>
      <label class="field"><span>Password again</span><input name="password2" type="password" minlength="10" autocomplete="new-password" required></label>
      <label class="agree"><input type="checkbox" name="agree" required> <span>I've read the <a href="privacy.html#members">privacy notice</a>
        and I'm happy for the network to keep my account details.</span></label>
      <div class="actions"><button class="btn btn-navy" type="submit">Create my account</button></div>
      <p class="form-msg hidden" role="status" data-msg></p>
    </form>
  </div>

  <div data-state="recover" class="hidden">
    <form class="mailform auth" data-newpass novalidate><h2>Choose a new password</h2>
      <label class="field"><span>New password</span><input name="password" type="password" minlength="10" autocomplete="new-password" required></label>
      <div class="actions"><button class="btn btn-navy" type="submit">Save my new password</button></div>
      <p class="form-msg hidden" role="status" data-msg></p></form>
  </div>

  <div data-state="in" class="hidden">
    <div class="member-top"><h2>Hello, <span data-hello></span></h2><button class="btn btn-line" type="button" data-signout>Sign out</button></div>
    <div class="tabs" role="tablist" data-tabs>
      <button type="button" role="tab" data-tab="profile" aria-selected="true">Your profile</button>
      <button type="button" role="tab" data-tab="foryou" aria-selected="false">For you</button>
      <button type="button" role="tab" data-tab="exclusives" aria-selected="false">Member exclusives</button>
      <button type="button" role="tab" data-tab="directory" aria-selected="false">Directory</button>
      <button type="button" role="tab" data-tab="account" aria-selected="false">Account</button>
    </div>
    <div data-panel="profile">{profile_form}</div>
    <div data-panel="foryou" class="hidden">
      <p class="lead-in">Picked from your profile's interests and, if you've turned it on, from what you open.</p>
      <div class="list" data-suggestions data-limit="20"></div><p class="learned" data-learned></p></div>
    <div data-panel="exclusives" class="hidden"><div class="papers" data-exclusives><p class="empty">Loading.</p></div></div>
    <div data-panel="directory" class="hidden">
      <label class="search"><span class="small muted">Search</span><input type="search" data-dir-search placeholder="Name, research area or skill"></label>
      <ul class="committee directory" data-directory></ul></div>
    <div data-panel="account" class="hidden account">
      <p>Signed in as <strong data-email-now></strong>.</p>
      <form class="mailform auth" data-email-change novalidate><h3>Change email</h3>
        <label class="field"><span>New email</span><input name="email" type="email" autocomplete="email" required></label>
        <div class="actions"><button class="btn btn-line" type="submit">Change email</button></div><p class="form-msg hidden" role="status" data-msg></p></form>
      <form class="mailform auth" data-pass-change novalidate><h3>Change password</h3>
        <label class="field"><span>New password</span><input name="password" type="password" minlength="10" autocomplete="new-password" required></label>
        <div class="actions"><button class="btn btn-line" type="submit">Change password</button></div><p class="form-msg hidden" role="status" data-msg></p></form>
      <div class="mailform auth"><h3>Your data</h3><p>Download everything we hold about you, as a file.</p>
        <div class="actions"><button class="btn btn-line" type="button" data-download>Download my data</button></div></div>
      <form class="mailform auth danger" data-delete novalidate><h3>Delete my account</h3>
        <p>This deletes your account and profile straight away, and can't be undone. Type your username to confirm.</p>
        <label class="field"><span>Username</span><input name="confirm" autocomplete="off" required></label>
        <div class="actions"><button class="btn btn-line" type="submit">Delete my account</button></div><p class="form-msg hidden" role="status" data-msg></p></form>
    </div>
  </div>
  <noscript><p class="note">The members' area needs JavaScript.</p></noscript>
</div></section>
<script src="{SUPABASE_JS[0]}" integrity="{SUPABASE_JS[1]}" crossorigin="anonymous" defer></script>
<script src="assets/members.js" defer></script>"""
    csp = CSP.replace("script-src 'self'", "script-src 'self' https://cdn.jsdelivr.net") \
             .replace("connect-src 'self'", f"connect-src 'self' {url}")
    return layout("members.html", "Members", body, "Your free members' account: profile, suggestions, exclusives and directory.", "members.html", csp=csp)


def committee_section() -> str:
    """Meet the committee: the photo, then each member with their role and the relationships they look after
    (content/committee.csv: name, role, relationships separated by ;)."""
    f = CONTENT / "committee.csv"
    if not f.exists():
        return ""
    people = list(csv.DictReader(f.open(encoding="utf-8-sig")))
    cards = "".join(
        f'''<li><h3>{esc(m["name"])}</h3><p class="role">{esc(m["role"])}</p>
  <p class="small muted">Looks after</p><ul>{"".join(f"<li>{esc(x.strip())}</li>" for x in m["relationships"].split(";") if x.strip())}</ul></li>'''
        for m in people)
    photo = ('<figure class="team-photo"><img src="images/committee.jpg" width="1600" height="1200" loading="lazy" '
             'alt="Eight members of the network on a staircase, smiling; the one in front holds the poster for our first talk, '
             'Radiological protection and the role of membership groups.">'
             '<figcaption class="small muted">The network with the poster for our first talk.</figcaption></figure>'
             if (CONTENT / "images" / "committee.jpg").exists() else "")
    return f'''<section class="section" id="committee"><div class="wrap">
  <div class="sec-head"><h2>{TRAIL}Meet the committee</h2></div>
  <p class="lead-in">We're PhD students who wanted a place for nuclear researchers at Liverpool to meet each other and the
    people they'll work with. Each of us looks after a few relationships, so if you'd like to work with one of these
    organisations, that's the person to talk to.</p>
  {photo}
  <ul class="committee">{cards}</ul>
</div></section>'''


def post_card(i: dict, kind: str) -> str:
    d = date_of(i.get("date"))
    by = f'<p class="byline">{esc(i["author"])}</p>' if i.get("author") else ""
    return (f'<article class="post">{f"<time datetime={d.isoformat()}>{fmt(d, False)}</time>" if d else ""}'
            f'<h3><a href="{kind}/{esc(i["slug"])}.html">{esc(i["title"])}</a></h3>{by}'
            f'<p class="muted">{inline(i.get("summary", ""))}</p></article>')


def main():
    sys.path.insert(0, str(HERE))
    offline = "--offline" in sys.argv
    if offline and (OUT / "events.json").exists():
        data = json.loads((OUT / "events.json").read_text(encoding="utf-8"))
        scraped, errors = [e for e in data["events"] if e["end"] >= TODAY.isoformat()], {}
    else:
        import scrape_events
        scraped, errors = scrape_events.collect()
        if errors and len(errors) == len(scrape_events.SOURCES):
            sys.exit("Every source failed: not publishing a site with no events")
    # start from a clean site/ (keeping nothing old), then the assets and pictures
    OUT.mkdir(exist_ok=True)
    for old in sorted(OUT.rglob("*"), reverse=True):   # empty site/: files first, then the folders that will let go
        try:                                             # (OneDrive or a preview server can hold a folder open)
            old.rmdir() if old.is_dir() else old.unlink()
        except OSError:
            pass
    shutil.copytree(HERE / "assets", OUT / "assets", dirs_exist_ok=True)
    if (CONTENT / "images").exists():
        shutil.copytree(CONTENT / "images", OUT / "images", dirs_exist_ok=True)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / "events.json").write_text(json.dumps(
        {"scraped": dt.datetime.now().isoformat(timespec="minutes"), "errors": errors, "events": scraped},
        indent=1, ensure_ascii=False), encoding="utf-8")
    with open(OUT / "events.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["start", "end", "org", "title", "location", "category", "url"], extrasaction="ignore")
        w.writeheader()
        w.writerows(scraped)
    build(scraped, errors)


if __name__ == "__main__":
    main()
