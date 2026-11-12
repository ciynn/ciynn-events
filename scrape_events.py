"""
CIYNN events scraper: collects upcoming events from nuclear membership groups and writes them
to site/index.html (the hosted page), site/events.csv and site/events.json.

Sources (one function each, below):
  NI    Nuclear Institute, including YGN and branch events (the site's own events feed)
  SRP   Society for Radiological Protection (news & events page)
  WiN   Women in Nuclear UK (its public iCal calendar feed)
  IPEM  Institute of Physics and Engineering in Medicine (all-events listing)
  IOP   Institute of Physics (events listing, kept only if the event looks nuclear-related)
  NIA   Nuclear Industry Association (all-upcoming-events page)

Run:   python scrape_events.py            (all sources; writes site/index.html)
       python scrape_events.py NI SRP     (only those sources)

It is polite by design: it checks each site's robots.txt, waits between requests, identifies
itself, and only reads public listing pages. If a site changes its layout, that one source
reports an error and the others still run.
"""
import csv
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
USER_AGENT = "CIYNN-events-digest/1.0 (Chadwick Institute Young Nuclear Network; ChadwickInstituteNetwork@outlook.com)"
DELAY = 1.5          # seconds between requests to the same site
TIMEOUT = 30
TODAY = dt.date.today()

# IOP lists all physics events; keep only those that mention one of these
NUCLEAR_WORDS = re.compile(
    r"nuclear|fusion|fission|radiation|radiolog|radioactiv|isotope|reactor|neutron|gamma|"
    r"particle|accelerator|medical physics|dosimetr|detector|decommission|tube alloys|plasma",
    re.I)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT
_robots: dict[str, urllib.robotparser.RobotFileParser] = {}
_last_request: dict[str, float] = {}


# --------------------------------------------------------------------------- helpers
def get(url: str, **kw) -> requests.Response:
    """GET a page, respecting robots.txt and a delay per site."""
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = session.get(host + "/robots.txt", timeout=TIMEOUT)
            rp.parse(r.text.splitlines() if r.ok else [])
        except requests.RequestException:
            rp.parse([])
        _robots[host] = rp
    if not _robots[host].can_fetch(USER_AGENT, url):
        raise PermissionError(f"robots.txt does not allow {url}")
    wait = DELAY - (time.time() - _last_request.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    r = session.get(url, timeout=TIMEOUT, **kw)
    _last_request[host] = time.time()
    r.raise_for_status()
    return r


def soup(url: str, **kw) -> BeautifulSoup:
    r = get(url, **kw)
    r.encoding = r.encoding or "utf-8"
    return BeautifulSoup(r.text, "html.parser")


def text(el) -> str:
    return " ".join(el.get_text(" ").split()) if el else ""


def month_num(word: str) -> int:
    return MONTHS[word[:3].lower()]


def next_occurrence(day: int, month: int) -> dt.date:
    """A date given without a year: the next time it comes round (allowing a month in the past)."""
    d = dt.date(TODAY.year, month, day)
    return d if d >= TODAY - dt.timedelta(days=31) else dt.date(TODAY.year + 1, month, day)


def event(org, title, start, end=None, location="", url="", category="", description=""):
    # Only facts are kept (title, dates, place, link). The organisations' own descriptions are
    # their copyright text, so they are not stored: people follow the link to read them.
    del description
    return {
        "org": org,
        "title": " ".join(html.unescape(title).split()),
        "start": start.isoformat() if start else "",
        "end": (end or start).isoformat() if start else "",
        "location": " ".join(location.split()),
        "category": category,
        "url": url,
    }


# --------------------------------------------------------------------------- sources
def scrape_ni():
    """Nuclear Institute: the JSON feed the events page itself uses. Covers YGN and branch events."""
    api = "https://www.nuclearinst.com/umbraco/api/customeventsapi/getevents"
    params = {"contentType": "events", "showFuture": "true", "showPast": "false",
              "parentListsToSearch": "1417", "limitFuture": "200", "itemCount": "50",
              "sortDirection": "2", "page": 1}
    out, pages = [], 1
    while params["page"] <= pages:
        data = get(api, params=params, headers={"Accept": "application/json"}).json()
        pages = data.get("totalPages", 1)
        for e in data.get("events", []):
            start = dt.date.fromisoformat(e["startDate"][:10]) if e.get("startDate") else None
            end = dt.date.fromisoformat(e["endDate"][:10]) if e.get("endDate") else None
            cats = e.get("categories") or []
            org = "NI YGN" if ("YGN" in e.get("name", "") or "YGN Events" in cats) else "NI"
            out.append(event(org, e.get("name", ""), start, end,
                             location=e.get("displayDate", "") if not start else "",
                             url=urljoin("https://www.nuclearinst.com", e.get("url", "")),
                             category=", ".join(cats), description=e.get("abstract", "")))
        params["page"] += 1
    return out


def _srp_dates(s: str):
    """'10th Dec 2026', '1st to 2nd Dec 2026', '30th Nov to 2nd Dec 2026'."""
    m = re.match(r"(\d+)\w*\s*(?:([A-Za-z]{3})\w*\s*(\d{4})?)?\s*(?:to\s*(\d+)\w*\s*([A-Za-z]{3})\w*\s*(\d{4}))?", s.strip())
    if not m:
        return None, None
    d1, mon1, y1, d2, mon2, y2 = m.groups()
    if d2:                                   # a range
        y2 = int(y2); mon2 = month_num(mon2)
        start = dt.date(int(y1) if y1 else y2, month_num(mon1) if mon1 else mon2, int(d1))
        return start, dt.date(y2, mon2, int(d2))
    d = dt.date(int(y1), month_num(mon1), int(d1))
    return d, d


def scrape_srp():
    s = soup("https://srp-uk.org/news-events")
    out = []
    for a in s.find_all("a", href=re.compile(r"^/event/|/events/SRP")):
        art = a.find_parent("article")
        if not art or not art.find("p", class_="date"):
            continue
        start, end = _srp_dates(text(art.find("p", class_="date")))
        out.append(event("SRP", text(a), start, end, location=text(art.find("p", class_="venue")),
                         url=urljoin("https://srp-uk.org", a["href"])))
    return out


def _ics_date(v: str) -> dt.date:
    return dt.date(int(v[0:4]), int(v[4:6]), int(v[6:8]))


def scrape_win():
    """Women in Nuclear UK: its public iCal feed."""
    t = get("https://www.winuk.org.uk/?post_type=tribe_events&ical=1&eventDisplay=list").text
    t = re.sub(r"\r?\n[ \t]", "", t)        # unfold folded lines
    out = []
    for block in t.split("BEGIN:VEVENT")[1:]:
        f = {}
        for line in block.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                f[k.split(";")[0]] = v.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";")
        if "DTSTART" not in f:
            continue
        out.append(event("WiN UK", f.get("SUMMARY", ""), _ics_date(f["DTSTART"]),
                         _ics_date(f.get("DTEND", f["DTSTART"])), location=f.get("LOCATION", ""),
                         url=f.get("URL", ""), category=f.get("CATEGORIES", ""),
                         description=f.get("DESCRIPTION", "")))
    return out


def scrape_ipem(max_pages=8):
    out = []
    for page in range(1, max_pages + 1):
        s = soup(f"https://www.ipem.ac.uk/what-s-on/all-events/?page={page}")
        cards = s.select("div.card")
        found = 0
        for c in cards:
            a = c.select_one("a.card-content__title")
            date = text(c.select_one(".card-content__date"))
            if not a or not date:
                continue
            ds = re.findall(r"(\d{2})/(\d{2})/(\d{4})", date)
            if not ds:
                continue
            start = dt.date(int(ds[0][2]), int(ds[0][1]), int(ds[0][0]))
            end = dt.date(int(ds[-1][2]), int(ds[-1][1]), int(ds[-1][0]))
            out.append(event("IPEM", text(a), start, end,
                             location=text(c.select_one(".card-content__time")),
                             url=urljoin("https://www.ipem.ac.uk", a["href"]),
                             description=text(c.select_one(".card-content__description"))))
            found += 1
        if not found:
            break
    return out


def scrape_iop(max_pages=10):
    out = []
    for page in range(0, max_pages):
        s = soup(f"https://www.iop.org/events?page={page}")
        blocks = s.select(".iop-media-block__inner")
        if not blocks:
            break
        for b in blocks:
            a = b.select_one("a.iop-media-block__cta")
            title = text(b.select_one(".iop-media-block__heading"))
            ps = b.select(".iop-media-block__date p")
            if not a or not ps:
                continue
            def d(p):
                m = re.search(r"(\d{1,2}) ([A-Za-z]{3}) (\d{4})", text(p))
                return dt.date(int(m.group(3)), month_num(m.group(2)), int(m.group(1))) if m else None
            start, end = d(ps[0]), d(ps[-1])
            if not NUCLEAR_WORDS.search(title):
                continue
            out.append(event("IOP", title, start, end,
                             location=text(b.select_one(".iop-media-block__event-type")),
                             url=urljoin("https://www.iop.org", a["href"])))
    return out


def scrape_nia():
    s = soup("https://www.niauk.org/all-upcoming-events/")
    out = []
    for p in s.find_all("p"):
        a = p.find("a", href=re.compile(r"niauk\.org/"))
        if not a or not p.find("br"):
            continue
        rest = text(p).replace(text(a), "", 1).strip(" |")
        m = re.search(r"(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s+([A-Za-z]+)(?:\s+(\d{4}))?", rest)
        if not m or m.group(3)[:3].lower() not in MONTHS:
            continue
        d1, d2, mon, yr = m.groups()
        mon = month_num(mon)
        yr = yr or (re.search(r"\b(20\d\d)\b", text(a)) or [None, None])[1]   # no year given: use one in the title
        start = dt.date(int(yr), mon, int(d1)) if yr else next_occurrence(int(d1), mon)
        end = start.replace(day=int(d2)) if d2 else start
        out.append(event("NIA", text(a), start, end, location=rest.split("|")[0].strip(), url=a["href"]))
    return out


SOURCES = {"NI": scrape_ni, "SRP": scrape_srp, "WiN": scrape_win,
           "IPEM": scrape_ipem, "IOP": scrape_iop, "NIA": scrape_nia}

# Groups whose events can't be read automatically: shown as links on the HTML page
MANUAL = [("BNMS (British Nuclear Medicine Society)", "https://www.bnms.org.uk/events"),
          ("AURPO", "https://www.aurpo.org.uk/")]


# --------------------------------------------------------------------------- output
def dedupe(events):
    """The same event on two sites (e.g. NI and NIA): same start date and one title contains the other.
    Keep the first and add the other organisation to it."""
    norm = lambda t: re.sub(r"[^a-z0-9]", "", t.lower())
    kept = []
    for e in events:
        for k in kept:
            a, b = norm(e["title"]), norm(k["title"])
            if e["start"] == k["start"] and (a in b or b in a):
                if e["org"] not in k["org"]:
                    k["org"] += " / " + e["org"]
                break
        else:
            kept.append(e)
    return kept


OUT = HERE / "site"          # the hosted page: site/index.html (+ events.csv and events.json)

# Filter buttons, in this order, with the label shown and the organisation codes they match
FILTERS = [("all", "All"), ("NI", "Nuclear Institute"), ("YGN", "YGN"), ("SRP", "SRP"),
           ("WiN", "WiN UK"), ("IPEM", "IPEM"), ("IOP", "IOP"), ("NIA", "NIA")]


def org_codes(org: str) -> list[str]:
    """'NI YGN / NIA' -> ['NI', 'YGN', 'NIA'] for the filter buttons."""
    codes = []
    for part in org.split(" / "):
        if part == "NI YGN":
            codes += ["NI", "YGN"]
        elif part == "WiN UK":
            codes.append("WiN")
        else:
            codes.append(part)
    return codes


def write_outputs(events, errors):
    OUT.mkdir(exist_ok=True)
    fields = ["start", "end", "org", "title", "location", "category", "url"]
    with open(OUT / "events.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(events)
    (OUT / "events.json").write_text(json.dumps(
        {"scraped": dt.datetime.now().isoformat(timespec="minutes"), "errors": errors, "events": events},
        indent=1, ensure_ascii=False), encoding="utf-8")

    def date_box(s, f):
        if s == f:
            return f"<b>{s.day}</b><span>{s.strftime('%b')}</span>"
        if (s.year, s.month) == (f.year, f.month):
            return f"<b>{s.day}–{f.day}</b><span>{s.strftime('%b')}</span>"
        return f"<b>{s.day}</b><span>{s.strftime('%b')}–{f.strftime('%b')}</span>"

    def when(s, f):
        fmt = lambda d: d.strftime("%a %d %b %Y").replace(" 0", " ")
        return fmt(s) if s == f else f"{fmt(s)} – {fmt(f)}"

    rows, month = [], None
    for e in events:
        s, f = dt.date.fromisoformat(e["start"]), dt.date.fromisoformat(e["end"])
        ongoing = s < TODAY                  # started already (e.g. a webinar series) and still running
        m = "ongoing" if ongoing else s.strftime("%Y-%m")
        if m != month:
            rows.append(f'<h2 data-month="{m}">{"Ongoing" if ongoing else s.strftime("%B %Y")}</h2>')
            month = m
        chips = "".join(f'<span class="org">{html.escape(o)}</span>' for o in e["org"].split(" / "))
        loc = f'<span>{html.escape(e["location"])}</span>' if e["location"] else ""
        cat = f'<span>{html.escape(e["category"])}</span>' if e["category"] else ""
        rows.append(
            f'<article class="ev" data-month="{m}" data-orgs="{" ".join(org_codes(e["org"]))}">'
            f'<div class="date">{date_box(s, f)}</div><div>'
            f'<h3><a href="{html.escape(e["url"])}" target="_blank" rel="noopener">{html.escape(e["title"])}</a></h3>'
            f'<div class="meta">{chips}<span class="when">{when(s, f)}</span>{loc}{cat}</div></div></article>')

    present = {c for e in events for c in org_codes(e["org"])}
    filters = "".join(
        f'<button type="button" data-org="{k}" aria-pressed="{str(k == "all").lower()}">{v}</button>'
        for k, v in FILTERS if k == "all" or k in present)
    also = "".join(f'<li><a href="{u}" target="_blank" rel="noopener">{html.escape(n)}</a></li>' for n, u in MANUAL)

    page = (HERE / "template.html").read_text(encoding="utf-8")
    for k, v in {"{{FILTERS}}": filters, "{{COUNT}}": str(len(events)),
                 "{{UPDATED}}": TODAY.strftime("%d %B %Y").lstrip("0"),
                 "{{EVENTS}}": "\n  ".join(rows), "{{ALSO}}": also}.items():
        page = page.replace(k, v)
    (OUT / "index.html").write_text(page, encoding="utf-8")


def main(names):
    events, errors = [], {}
    for name in names:
        try:
            got = SOURCES[name]()
            print(f"{name:5} {len(got):3} events")
            events += got
        except Exception as exc:            # one broken site shouldn't stop the rest
            errors[name] = f"{type(exc).__name__}: {exc}"
            print(f"{name:5} ERROR {errors[name]}")
    events = [e for e in events if e["start"] and dt.date.fromisoformat(e["end"]) >= TODAY]
    events = sorted(dedupe(events), key=lambda e: (e["start"], e["org"], e["title"]))
    write_outputs(events, errors)
    print(f"{len(events)} upcoming events -> {OUT / 'index.html'} (+ events.csv, events.json)")
    if errors and len(errors) == len(names):
        sys.exit("Every source failed: not publishing an empty page")


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(SOURCES)
    bad = [n for n in wanted if n not in SOURCES]
    if bad:
        sys.exit(f"Unknown source(s): {', '.join(bad)}. Choose from: {', '.join(SOURCES)}")
    main(wanted)
