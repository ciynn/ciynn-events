# Chadwick Institute Young Nuclear Network website

The network's website: our events, an events digest from the UK's nuclear membership groups, upcoming
conferences by field, news, member articles, opportunities, joining, partnering and an about page.

It is a static site, rebuilt every Monday (and on every push) by a GitHub Action, so it needs no server,
database or passwords.

## Pages

| Page | What it shows | Where it comes from |
|---|---|---|
| Home | next event, the next UK events and conferences, latest news, partner call | everything below |
| Events | our events (with sign-up), then the UK digest with filters and search | `content/events/`, scraped |
| Conferences | upcoming conferences by field, with filters and search, and a directory of conference series | scraped, `content/conferences.csv`, `content/conference_series.csv` |
| News | posts | `content/news/` |
| Articles | writing by members, and how to write for us | `content/articles/` |
| Opportunities | PhDs, jobs and placements; each drops off after its closing date | `content/opportunities/` |
| Join | who it's for, what you get, the sign-up form | `build_site.py` (`JOIN_FIELDS`) |
| Partners | partnership levels, how it works, our commitments, the register-interest form | `build_site.py` (`PARTNER_FIELDS`) |
| About, Privacy | who we are, aims, how we're run, contact; how we handle data | `build_site.py` |

Plus `feed.xml` (RSS for the news), `sitemap.xml`, `events.json` and `events.csv`.

## Run it

```bash
pip install -r requirements.txt
python build_site.py              # scrape all sources, then build site/
python build_site.py --offline    # rebuild from the last scrape, without going online
python -m http.server -d site     # then open http://localhost:8000
```

## Add things

Every content file is Markdown with a short header. Files whose names start with `_` are skipped.

**A news post**: `content/news/2026-12-01-short-name.md`

```
---
title: The headline
date: 2026-12-01
summary: One or two sentences for the home page and the news list.
---
The text. A blank line between paragraphs, ## for a heading, - for a list, **bold**, *italic*,
[link text](https://...).
```

**A member article**: the same in `content/articles/`, with `author:` and `role:` in the header
(see `content/articles/_how_to_add_an_article.md`). Check before it goes up: the author has agreed,
nothing is confidential, commercially sensitive or export-controlled, and every picture is ours or used
with permission. Pictures go in `content/images/`.

**One of our events**: `content/events/2027-02-10-short-name.md` with `title`, `date` (or `TBC` plus
`deadline`), `time`, `place`, `speaker`, `who`, `signup` (a link, or `mailto` for "email us") and
`signup_label`. Past events move to a "Past events" list by themselves.

**An opportunity**: `content/opportunities/` with `title`, `organisation`, `type`, `closes` and `url`.

**A conference the scrapers miss**: a row in `content/conferences.csv`
(`title,field,organiser,start,end,location,url,deadline`, dates as 2027-06-21). `field` is one of the
filter names on the page; leave it empty to have it guessed from the title.

## Sign-up, partner and article forms

The Join, Partners and Articles pages each have a form. Pressing its button checks the required boxes, then
opens the visitor's own email app with a message to the network's mailbox (`email` in `site.json`) already
written: the subject (e.g. "Join the network: Ada Lovelace") and every answer, one per line. The visitor
checks it and presses send. Article writers attach their file in that email. If no email app opens, the
page offers to copy the message so it can be pasted into webmail.

So nothing needs setting up, and the website, GitHub and no form service ever see or store anyone's
details: sign-ups simply arrive in the Outlook inbox. To change the questions, edit `JOIN_FIELDS`,
`PARTNER_FIELDS` or `ARTICLE_FIELDS` in `build_site.py`.

## Sources and how they are read

| Source | What is read |
|---|---|
| Nuclear Institute (NI), including YGN and branch events | the public events feed used by nuclearinst.com/events-conferences |
| Society for Radiological Protection (SRP) | srp-uk.org/news-events |
| Women in Nuclear UK (WiN UK) | the public iCal feed on winuk.org.uk/events |
| Institute of Physics and Engineering in Medicine (IPEM) | ipem.ac.uk/what-s-on/all-events |
| Institute of Physics (IOP) | iop.org/events, keeping only nuclear-related events |
| Nuclear Industry Association (NIA) | niauk.org/all-upcoming-events |
| IAEA | conferences.iaea.org, the Conferences category; technical meetings (by nomination) are left out |

BNMS and AURPO can't be read automatically, so the events page links to them. NuPECC's site asks not to be
read automatically (its robots.txt), so it is only linked from the conference directory.

The scrapers read only public listing pages, follow each site's `robots.txt`, wait between requests and
identify themselves. They keep only facts (title, dates, place, organiser, link): descriptions and images
stay on the organisers' sites. If one site changes its layout, that source reports an error and the
others still run.

## Safety

- No cookies, analytics, trackers or third-party scripts; the only outside requests are Google Fonts.
- A Content Security Policy in every page allows scripts only from the site itself.
- Content files are turned into HTML by a small Markdown converter that escapes everything first, so raw
  HTML or scripts in a post are shown as text, never run, and only http(s), mailto and relative links work.
- Links that leave the site open in a new tab with `rel="noopener noreferrer"`.
- No mailing lists, form responses or other personal data are kept in this repository.

## Publishing

The workflow `.github/workflows/update-events.yml` builds the site and, when the repository variable
`PUBLISH_PAGES` is `true`, publishes it to GitHub Pages at https://ciynn.github.io/ciynn-events/.
For a shorter address (https://ciynn.github.io/), rename the repository to `ciynn.github.io` and change
`base_url` in `site.json` to match.
