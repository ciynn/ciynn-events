"""
CIYNN events scraper: collects upcoming events and conferences from nuclear membership groups and
international bodies. build_site.py uses it to make the website; run on its own it prints the list.

Sources (one function each, below):
  NI    Nuclear Institute, including YGN and branch events (the site's own events feed)
  SRP   Society for Radiological Protection (news & events page)
  WiN   Women in Nuclear UK (its public iCal calendar feed)
  IPEM  Institute of Physics and Engineering in Medicine (all-events listing)
  IOP   Institute of Physics (events listing, kept only if the event looks nuclear-related)
  NIA   Nuclear Industry Association (all-upcoming-events page)
  IAEA  International Atomic Energy Agency conferences (conferences.iaea.org; open meetings only)
  ANS   American Nuclear Society conferences (ans.org/meetings)
  NPSS  IEEE Nuclear and Plasma Sciences Society conferences (ieee-npss.org/conferences)
  EPS   European Physical Society calendar (its iCal feed), nuclear and plasma meetings only

Run:   python scrape_events.py            (all sources; prints what it found)
       python scrape_events.py NI SRP     (only those sources)

It is polite by design: it checks each site's robots.txt, waits between requests, identifies
itself, and only reads public listing pages. If a site changes its layout, that one source
reports an error and the others still run.
"""
import datetime as dt
import html
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


def tidy_place(s: str) -> str:
    """'Bologna, Italy, Bologna,, Italy' -> 'Bologna, Italy'."""
    parts = []
    for x in " ".join((s or "").split()).split(","):
        x = x.strip()
        if x and x.lower() not in [p.lower() for p in parts]:
            parts.append(x)
    return ", ".join(parts)


def event(org, title, start, end=None, location="", url="", category="", description=""):
    # Only facts are kept (title, dates, place, link). The organisations' own descriptions are
    # their copyright text, so they are not stored: people follow the link to read them.
    del description
    return {
        "org": org,
        "title": " ".join(html.unescape(title).replace(chr(0x200E), "").split()),
        "start": start.isoformat() if start else "",
        "end": (end or start).isoformat() if start else "",
        "location": tidy_place(location),
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


def read_ics(url: str) -> list[dict]:
    """The events in a public iCal feed, as dicts of their fields (SUMMARY, DTSTART, LOCATION, URL, ...)."""
    t = re.sub(r"\r?\n[ \t]", "", get(url).text)        # unfold folded lines
    out = []
    for block in t.split("BEGIN:VEVENT")[1:]:
        f = {}
        for line in block.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                f[k.split(";")[0]] = v.replace("\\,", ",").replace("\\n", " ").replace("\\;", ";")
        if "DTSTART" in f:
            out.append(f)
    return out


def _ics_end(f) -> dt.date:
    """An all-day DTEND is the day after the event ends."""
    end = _ics_date(f.get("DTEND", f["DTSTART"]))
    if len(f.get("DTEND", "")) == 8 and end > _ics_date(f["DTSTART"]):
        end -= dt.timedelta(days=1)
    return end


def scrape_win():
    """Women in Nuclear UK: its public iCal feed."""
    return [event("WiN UK", f.get("SUMMARY", ""), _ics_date(f["DTSTART"]), _ics_end(f),
                  location=f.get("LOCATION", ""), url=f.get("URL", ""), category=f.get("CATEGORIES", ""))
            for f in read_ics("https://www.winuk.org.uk/?post_type=tribe_events&ical=1&eventDisplay=list")]


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
                             category=text(c.select_one(".card-content__time")),
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
                             category=text(b.select_one(".iop-media-block__event-type")),
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


def _iaea_months(html_text):
    """Indico's event list: month headings ('November 2026') then items with '24 Nov - 27 Nov'."""
    out = []
    b = BeautifulSoup(html_text, "html.parser")
    for h in b.find_all("h3"):
        m = re.match(r"([A-Za-z]+) (\d{4})", text(h))
        ul = h.find_next_sibling("ul")
        if not m or m.group(1)[:3].lower() not in MONTHS or not ul:
            continue
        year = int(m.group(2))
        for li in ul.find_all("li", recursive=False):
            a = li.select_one(".event-title a")
            d = re.findall(r"(\d{1,2}) ([A-Za-z]{3})", text(li.select_one(".date")))
            if not a or not d:
                continue
            start = dt.date(year, month_num(d[0][1]), int(d[0][0]))
            em = month_num(d[-1][1])
            end = dt.date(year + (em < start.month), em, int(d[-1][0]))
            out.append((a, start, end))
    return out


# IAEA technical meetings are by nomination only, so keep the open ones
IAEA_OPEN = re.compile(r"conference|symposium|congress|school|workshop|forum", re.I)


def scrape_iaea():
    """IAEA conferences (conferences.iaea.org, an Indico site): the category page, then the rest of the
    future list from the same JSON endpoint the page itself loads."""
    base = "https://conferences.iaea.org/category/1/"
    page = get(base).text
    items = _iaea_months(page[page.find("future-events"):] if "future-events" in page else page)
    m = re.search(r'data-event-list-after="([\d-]+)"', page)
    if m:
        items += _iaea_months(get(base + "event-list", params={"after": m.group(1)},
                                  headers={"Accept": "application/json"}).json().get("html", ""))
    out, seen = [], set()
    for a, start, end in items:
        title = text(a)
        if not IAEA_OPEN.search(title) or a["href"] in seen:
            continue
        seen.add(a["href"])
        url = urljoin(base, a["href"])
        try:                                   # the venue is on the event's own page
            place = text(soup(url).select_one(".infoline.location .place"))
        except Exception:
            place = ""
        if re.fullmatch(r"(VIC|IAEA\W*(HQ|Headquarters).*|Vienna International Cent(re|er).*)", place or "", re.I):
            place = "Vienna, Austria"
        out.append(event("IAEA", title, start, end, location=place, url=url, category="Conference"))
    return out


def _us_dates(s: str):
    """'November 15-18, 2026', 'May 30-June 3, 2027', 'June 13, 2027' (any dash)."""
    s = re.sub(r"[‒-―]", "-", s)
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2})(?:\s*-\s*(?:([A-Za-z]+)\s+)?(\d{1,2}))?,\s*(\d{4})", s.strip())
    if not m:
        return None, None
    m1, d1, m2, d2, y = m.groups()
    start = dt.date(int(y), month_num(m1), int(d1))
    end = dt.date(int(y), month_num(m2 or m1), int(d2 or d1))
    return start, (end if end >= start else end.replace(year=end.year + 1))


def scrape_ans():
    """American Nuclear Society: upcoming conferences."""
    out = []
    for ev in soup("https://www.ans.org/meetings/").select("div.event"):
        a, when = ev.select_one("p.title a"), ev.select_one("p.callout")
        if not a or not when:
            continue
        start, end = _us_dates(text(when))
        place = text(ev.select_one("p.location")).split("|")[0].strip()
        out.append(event("ANS", text(a), start, end, location=place, url=a["href"], category="Conference"))
    return out


def scrape_npss():
    """IEEE Nuclear and Plasma Sciences Society: its conference table (NSS/MIC, SOFE, ICOPS, ...)."""
    out = []
    for tr in soup("https://ieee-npss.org/conferences/").select("tr.conference"):
        a, times = tr.select_one(".conference__name a"), tr.select("time[datetime]")
        if not a or not times:
            continue
        start = dt.date.fromisoformat(times[0]["datetime"][:10])
        end = dt.date.fromisoformat(times[-1]["datetime"][:10])
        lines = [x.strip() for x in tr.select("td")[-1].get_text("\n").split("\n") if x.strip()]
        place = next((x for x in lines if re.search(r"[A-Za-z]{3}", x) and not re.search(r"\d|register", x, re.I)), "")
        short = re.sub(r"\b(NPSS|TCO|CO)\b", "", text(tr.select_one(".conference__meta__short-name"))).strip()
        short = re.sub(r"^\d{4}\s*", "", short)
        title = text(a) + (f" ({short})" if short and short not in text(a) else "")
        out.append(event("IEEE NPSS", title, start, end, location=place, url=a["href"].strip(), category="Conference"))
    return out


def scrape_eps():
    """European Physical Society: its public calendar, keeping nuclear, plasma and related meetings."""
    out = []
    for f in read_ics("https://eps.org/events/?ical=1"):
        words = " ".join(f.get(k, "") for k in ("SUMMARY", "CATEGORIES", "DESCRIPTION"))
        if not NUCLEAR_WORDS.search(words):
            continue
        out.append(event("EPS", f.get("SUMMARY", ""), _ics_date(f["DTSTART"]), _ics_end(f),
                         location=f.get("LOCATION", ""), url=f.get("URL", ""), category="Conference"))
    return out


SOURCES = {"NI": scrape_ni, "SRP": scrape_srp, "WiN": scrape_win,
           "IPEM": scrape_ipem, "IOP": scrape_iop, "NIA": scrape_nia,
           "IAEA": scrape_iaea, "ANS": scrape_ans, "NPSS": scrape_npss, "EPS": scrape_eps}

# Sources that list conferences rather than events (they go on the conferences page only)
CONFERENCE_ORGS = {"IAEA", "ANS", "IEEE NPSS", "EPS"}

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


def collect(names=None):
    """Run the chosen sources (all by default). Returns (upcoming events, errors by source)."""
    events, errors = [], {}
    for name in names or list(SOURCES):
        try:
            got = SOURCES[name]()
            print(f"{name:5} {len(got):3} items")
            events += got
        except Exception as exc:            # one broken site shouldn't stop the rest
            errors[name] = f"{type(exc).__name__}: {exc}"
            print(f"{name:5} ERROR {errors[name]}")
    events = [e for e in events if e["start"] and dt.date.fromisoformat(e["end"]) >= TODAY]
    return sorted(dedupe(events), key=lambda e: (e["start"], e["org"], e["title"])), errors


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(SOURCES)
    bad = [n for n in wanted if n not in SOURCES]
    if bad:
        sys.exit(f"Unknown source(s): {', '.join(bad)}. Choose from: {', '.join(SOURCES)}")
    found, errs = collect(wanted)
    for e in found:
        print(f'{e["start"]}  {e["org"]:8}  {e["title"]}')
    print(f"{len(found)} upcoming, errors: {errs or 'none'}")
