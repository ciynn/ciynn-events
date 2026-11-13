"""
The conference world map: an inline SVG (no map service, no outside requests from the page).

  land        content/world-land-110m.json, Natural Earth 1:110m land (public domain) as TopoJSON
              (world-atlas 2.0.2), drawn in the Equal Earth projection
  places      looked up once with the Open-Meteo geocoding API (GeoNames data, CC BY 4.0) and kept in
              content/geocache.json, so each place is only ever looked up once
"""
import html
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAND = HERE / "content" / "world-land-110m.json"
CACHE = HERE / "content" / "geocache.json"
WIDTH = 1000.0
LAT_MIN = -57.0                                    # leave out Antarctica

# --------------------------------------------------------------------------- Equal Earth projection
A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
_M = math.sqrt(3) / 2
_X_MAX = 2.706629                                  # x at longitude 180, latitude 0
_SCALE = WIDTH / (2 * _X_MAX)


def _ee(lon: float, lat: float) -> tuple[float, float]:
    lam, phi = math.radians(lon), math.radians(lat)
    t = math.asin(_M * math.sin(phi))
    t2 = t * t
    t6 = t2 * t2 * t2
    x = lam * math.cos(t) / (_M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)))
    y = t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, y


_Y_TOP = _ee(0, 84)[1]
_Y_BOTTOM = _ee(0, LAT_MIN)[1]
HEIGHT = round((_Y_TOP - _Y_BOTTOM) * _SCALE, 1)


def project(lon: float, lat: float) -> tuple[float, float]:
    x, y = _ee(lon, max(lat, LAT_MIN))
    return round((x + _X_MAX) * _SCALE, 1), round((_Y_TOP - y) * _SCALE, 1)


# --------------------------------------------------------------------------- land outline from TopoJSON
def land_path() -> str:
    topo = json.loads(LAND.read_text(encoding="utf-8"))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:                      # delta-encoded, quantised
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)

    def ring(indices):
        pts = []
        for i in indices:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts += a[1:] if pts else a
        return pts

    d = []
    for geom in topo["objects"]["land"]["geometries"]:
        polys = geom["arcs"] if geom["type"] == "MultiPolygon" else [geom["arcs"]]
        for poly in polys:
            for r in poly:
                pts = ring(r)
                if min(lat for _, lat in pts) < -60:          # Antarctica
                    continue
                pieces, xy, last, plon = [], [], None, None
                for lon, lat in pts:
                    if plon is not None and abs(lon - plon) > 180:   # crosses the 180th meridian: start a new piece
                        pieces.append(xy)
                        xy, last = [], None
                    p = project(lon, lat)
                    if p != last:
                        xy.append(p)
                        last = p
                    plon = lon
                pieces.append(xy)
                for xy in pieces:
                    if len(xy) > 2:
                        d.append("M" + "L".join(f"{x:g},{y:g}" for x, y in xy) + "Z")
    return "".join(d)


# --------------------------------------------------------------------------- places
NOT_A_PLACE = re.compile(r"^(online|virtual|webinar|hybrid|in[- ]person|tbc|tba|various|teams|zoom)\b|^\W*$|^[\d:\s.-]+$", re.I)
US_STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
             "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
             "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
             "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
             "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
             "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
             "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
             "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
             "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
             "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"}
VENUE_WORDS = re.compile(r"\b(international|convention|conference|exhibition|congress|events?|cent(re|er)|hall|hotel|"
                         r"resort|spa|campus|headquarters|university( of)?|the)\b", re.I)
COUNTRY_ALIASES = {"usa": "united states", "us": "united states", "uk": "united kingdom", "england": "united kingdom",
                   "scotland": "united kingdom", "wales": "united kingdom", "korea": "south korea",
                   "republic of korea": "south korea", "czechia": "czech republic"}


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def geocode_all(places: set[str], get) -> dict:
    """{place: (lat, lon, label) or None}. `get` is scrape_events.get (robots.txt, delay, user agent)."""
    cache = _load_cache()
    changed = False
    for place in sorted(p for p in places if p and p not in cache):
        cache[place] = None
        if not NOT_A_PLACE.search(place):
            try:
                cache[place] = _lookup(place, get)
            except Exception as exc:              # leave it off the map this time; try again next build
                print(f"  geocoding '{place}' failed: {exc}")
                del cache[place]
                continue
        changed = True
    if changed:
        CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return {p: cache.get(p) for p in places}


def _lookup(place: str, get):
    parts = [p.strip() for p in place.split(",") if p.strip()]
    hints = {h.lower() for h in parts[1:]}
    hints |= {US_STATES[h.upper()].lower() for h in parts[1:] if h.upper() in US_STATES}
    hints |= {COUNTRY_ALIASES[h] for h in hints if h in COUNTRY_ALIASES}
    states = {US_STATES[h.upper()].lower() for h in parts[1:] if h.upper() in US_STATES} | \
             {h.lower() for h in parts[1:] if h.lower() in {v.lower() for v in US_STATES.values()}}
    for name in parts[:2]:                         # the first part is usually the city; else try the next
        name = re.sub(r"\(.*?\)", "", name)
        name = VENUE_WORDS.sub("", name).strip(" -")
        if len(name) < 3:
            continue
        r = get("https://geocoding-api.open-meteo.com/v1/search",
                params={"name": name, "count": 10, "language": "en", "format": "json"}).json()
        res = r.get("results") or []
        if not res:
            continue

        def score(x):                              # the right state beats just the right country
            s = 2 if str(x.get("admin1", "")).lower() in states else 0
            return s + (1 if hints & {str(x.get(k, "")).lower() for k in ("country", "country_code", "admin1")} else 0)
        ranked = sorted(res, key=score, reverse=True)
        best = [x for x in ranked if score(x) > 0][:1] if hints else ranked[:1]
        if best:
            b = best[0]
            label = f'{b["name"]}, {b.get("country", "")}'.strip(", ")
            return [round(b["latitude"], 3), round(b["longitude"], 3), label]
    return None


# --------------------------------------------------------------------------- the map
def place_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def map_svg(points: dict) -> str:
    """points: {label: (lat, lon, count)}. Returns the <svg> with one focusable dot per place."""
    dots = []
    for label, (lat, lon, n) in sorted(points.items(), key=lambda kv: -kv[1][2]):    # big ones underneath
        x, y = project(lon, lat)
        r = round(4.5 + 2.6 * math.sqrt(n), 1)
        what = f"{n} conference{'s' if n != 1 else ''}"
        e = html.escape(label)
        dots.append(f'<a href="#map-list" class="dot" data-place-btn="{place_key(label)}" data-label="{e}" '
                    f'aria-label="{e}: {what}"><title>{e}: {what}</title>'
                    f'<circle cx="{x}" cy="{y}" r="{r + 6}" class="hit"/><circle cx="{x}" cy="{y}" r="{r}"/>'
                    + (f'<text x="{x}" y="{y + 4}">{n}</text>' if n > 1 else "") + "</a>")
    return (f'<svg viewBox="0 0 {WIDTH:g} {HEIGHT:g}" role="group" aria-label="World map of upcoming conferences">'
            f'<path class="land" d="{land_path()}"/>{"".join(dots)}</svg>')
