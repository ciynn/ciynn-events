# CIYNN events scraper

Collects upcoming events from UK nuclear membership groups into one list, so the
Chadwick Institute Young Nuclear Network can point its members to them.

| Source | What is read |
|---|---|
| Nuclear Institute (NI), including YGN and branch events | the public events feed used by nuclearinst.com/events-conferences |
| Society for Radiological Protection (SRP) | srp-uk.org/news-events |
| Women in Nuclear UK (WiN UK) | the public iCal feed on winuk.org.uk/events |
| Institute of Physics and Engineering in Medicine (IPEM) | ipem.ac.uk/what-s-on/all-events |
| Institute of Physics (IOP) | iop.org/events, keeping only nuclear-related events |
| Nuclear Industry Association (NIA) | niauk.org/all-upcoming-events |

BNMS and AURPO can't be read automatically, so the page links to them instead.

## Run

```bash
pip install requests beautifulsoup4
python scrape_events.py            # all sources
python scrape_events.py NI SRP     # only some
```

Output (not kept in the repository) goes in `site/`: `index.html`, a page in the network's
style with the events grouped by month, filter buttons by organisation and a link to each
event's own page, plus `events.csv` and `events.json`. The page layout is in `template.html`.

## Hosting (GitHub Pages)

`.github/workflows/update-events.yml` re-runs the scraper every Monday at 06:00 UTC (and on
every push, or by hand from the Actions tab) and publishes `site/` to GitHub Pages.
Publishing is off until you switch it on. Once the repository is public:
1. Settings → Pages → Source: **GitHub Actions**.
2. Settings → Secrets and variables → Actions → Variables: add `PUBLISH_PAGES` = `true`.
3. Actions → Update events page → **Run workflow**.

The page then appears at `https://<user>.github.io/<repository>/`. Until then the weekly run
still builds the page (a check that every source still works) but doesn't publish it.

## How it behaves

- Reads only public listing pages, and follows each site's `robots.txt`.
- Waits between requests to the same site and identifies itself in its user agent.
- Keeps only facts: title, dates, place, organiser and a link. Descriptions and images
  are not copied; readers follow the link to the organiser's page for details and booking.
- If one site changes its layout, that source reports an error and the others still run.

All event information belongs to the organisation that published it.
