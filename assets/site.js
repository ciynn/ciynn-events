// Chadwick Institute Young Nuclear Network website: menu, list filters, search and copy buttons.
// No tracking, no cookies, no storage, and nothing is sent anywhere.
(function () {
  'use strict';

  // Mobile menu
  var btn = document.querySelector('.menu-btn'), nav = document.getElementById('nav');
  if (btn && nav) {
    btn.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      btn.setAttribute('aria-expanded', String(open));
      btn.textContent = open ? 'Close' : 'Menu';
    });
  }

  // Filterable lists: <div data-filter-list> with .chips buttons (data-value) and rows (data-tags),
  // an optional search box (data-search) and month headings (data-month) that hide when empty
  document.querySelectorAll('[data-filter-list]').forEach(function (box) {
    var chips = box.querySelectorAll('.chips button'), rows = box.querySelectorAll('[data-tags]');
    var months = box.querySelectorAll('[data-month-head]'), search = box.querySelector('[data-search]');
    var shown = box.querySelector('[data-shown]'), none = box.querySelector('[data-none]');
    var value = 'all', place = '';
    var dots = box.querySelectorAll('[data-place-btn]'), note = box.querySelector('[data-place-note]');
    function apply() {
      var q = search ? search.value.trim().toLowerCase() : '', n = 0, live = {};
      rows.forEach(function (r) {
        var byField = (value === 'all' || r.dataset.tags.split(' ').indexOf(value) >= 0) &&
                      (!q || r.textContent.toLowerCase().indexOf(q) >= 0);
        var on = byField && (!place || r.dataset.place === place);
        if (byField && r.dataset.place) live[r.dataset.place] = true;
        r.classList.toggle('hidden', !on);
        if (on) n++;
      });
      // map: dim places with nothing under the current field and search; mark the chosen one
      dots.forEach(function (d) {
        d.classList.toggle('dim', !live[d.dataset.placeBtn]);
        d.classList.toggle('on', d.dataset.placeBtn === place);
      });
      if (note) note.classList.toggle('hidden', !place);
      months.forEach(function (m) {
        m.classList.toggle('hidden', !box.querySelector('[data-month="' + m.dataset.monthHead + '"]:not(.hidden)'));
      });
      if (shown) shown.textContent = n;
      if (none) none.classList.toggle('hidden', n > 0);
    }
    chips.forEach(function (c) {
      c.addEventListener('click', function () {
        chips.forEach(function (x) { x.setAttribute('aria-pressed', String(x === c)); });
        value = c.dataset.value;
        apply();
      });
    });
    if (search) search.addEventListener('input', apply);
    dots.forEach(function (d) {
      d.addEventListener('click', function (ev) {
        ev.preventDefault();
        place = place === d.dataset.placeBtn ? '' : d.dataset.placeBtn;     // a second click shows every place again
        if (note) note.querySelector('[data-place-name]').textContent = d.dataset.label;
        apply();
        var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (place && note) note.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'nearest' });
      });
    });
    var clear = box.querySelector('[data-place-clear]');
    if (clear) clear.addEventListener('click', function () { place = ''; apply(); });
  });

  // Email forms: on Send, check the boxes, then open the visitor's email app with the message written out.
  // The page itself sends and stores nothing: the visitor sees the email and sends it themselves.
  function copyText(text, button) {
    var done = function () { var t = button.textContent; button.textContent = 'Copied'; setTimeout(function () { button.textContent = t; }, 1800); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { window.prompt('Copy this message:', text); });
    } else { window.prompt('Copy this message:', text); }
  }
  document.querySelectorAll('[data-mailform]').forEach(function (form) {
    var message = '';
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var bad = [];
      form.querySelectorAll('input, select, textarea').forEach(function (el) {
        var field = el.closest('.field, .agree');
        var ok = el.checkValidity();
        if (field) field.classList.toggle('invalid', !ok);
        if (!ok) bad.push(el);
      });
      form.querySelector('[data-error]').classList.toggle('hidden', bad.length === 0);
      if (bad.length) { bad[0].focus(); return; }

      var lines = [], seen = {};
      form.querySelectorAll('input, select, textarea').forEach(function (el) {
        var name = el.name;
        if (!name || seen[name]) return;
        if (el.type === 'checkbox' && el.closest('.boxes')) {
          seen[name] = true;
          var ticked = Array.prototype.map.call(form.querySelectorAll('.boxes input[name="' + CSS.escape(name) + '"]:checked'), function (c) { return c.value; });
          lines.push(name + ': ' + (ticked.join(', ') || '-'));
        } else if (el.type === 'checkbox') {
          lines.push((el.checked ? '[x] ' : '[ ] ') + name);
        } else {
          lines.push(name + ': ' + (el.value.trim() || '-'));
        }
      });
      var who = form.querySelector('[name="' + CSS.escape(form.dataset.subjectField) + '"]');
      var subject = form.dataset.subject + (who && who.value.trim() ? ': ' + who.value.trim() : '');
      message = lines.join('\n') + '\n\n(Sent from the network website.)';
      form.querySelector('[data-sent]').classList.remove('hidden');
      window.location.href = 'mailto:' + form.dataset.to + '?subject=' + encodeURIComponent(subject) +
        '&body=' + encodeURIComponent(message);
      form.dataset.lastSubject = subject;
    });
    var copy = form.querySelector('[data-copy-form]');
    if (copy) copy.addEventListener('click', function () {
      copyText('To: ' + form.dataset.to + '\nSubject: ' + (form.dataset.lastSubject || form.dataset.subject) + '\n\n' + message, copy);
    });
    form.addEventListener('input', function (ev) {
      var field = ev.target.closest('.invalid');
      if (field && ev.target.checkValidity()) field.classList.remove('invalid');
    });
  });

  // Zoomable map: wheel or pinch to zoom, drag to move, buttons for keyboard and phones. Markers keep their
  // size on screen as you zoom, so close-together places separate.
  document.querySelectorAll('svg[data-zoomable]').forEach(function (svg) {
    var frame = svg.parentNode, box = svg.getAttribute('viewBox').split(/[\s,]+/).map(Number);
    var W = box[2], H = box[3], vb = { x: 0, y: 0, w: W, h: H }, MAX = 8;
    var sized = svg.querySelectorAll('[data-r], [data-fs]'), pending = false, dragged = false;
    function draw() {
      pending = false;
      svg.setAttribute('viewBox', vb.x + ' ' + vb.y + ' ' + vb.w + ' ' + vb.h);
      var k = W / vb.w, s = 1 / Math.pow(k, 0.75);        // markers shrink a little less than the map grows
      sized.forEach(function (el) {
        if (el.dataset.r) el.setAttribute('r', (el.dataset.r * s).toFixed(2));
        if (el.dataset.fs) el.style.fontSize = (el.dataset.fs * s).toFixed(2) + 'px';
      });
      svg.querySelectorAll('text[data-dy]').forEach(function (t) {
        t.setAttribute('transform', 'translate(0 ' + (-(t.dataset.dy) * (1 - s)).toFixed(2) + ')');
      });
      svg.style.touchAction = k > 1.01 ? 'none' : 'pan-y';   // at full size, let the page scroll over the map
      frame.classList.toggle('zoomed', k > 1.01);
    }
    function redraw() { if (!pending) { pending = true; requestAnimationFrame(draw); } }
    function clamp() {
      vb.w = Math.min(W, Math.max(W / MAX, vb.w)); vb.h = vb.w * H / W;
      vb.x = Math.min(W - vb.w, Math.max(0, vb.x)); vb.y = Math.min(H - vb.h, Math.max(0, vb.y));
    }
    function point(cx, cy) {                               // screen point -> map coordinates
      var r = svg.getBoundingClientRect();
      return { x: vb.x + (cx - r.left) / r.width * vb.w, y: vb.y + (cy - r.top) / r.height * vb.h, fx: (cx - r.left) / r.width, fy: (cy - r.top) / r.height };
    }
    function zoomAt(factor, cx, cy) {
      var r = svg.getBoundingClientRect();
      var p = cx === undefined ? { x: vb.x + vb.w / 2, y: vb.y + vb.h / 2, fx: .5, fy: .5 } : point(cx, cy);
      vb.w /= factor; vb.h = vb.w * H / W;
      vb.x = p.x - p.fx * vb.w; vb.y = p.y - p.fy * vb.h;
      clamp(); redraw();
    }
    svg.addEventListener('wheel', function (ev) {
      if (!ev.ctrlKey && W / vb.w <= 1.01 && ev.deltaY > 0) return;   // zooming out at full size: scroll the page
      ev.preventDefault();
      zoomAt(Math.exp(-ev.deltaY * (ev.deltaMode ? 0.05 : 0.0018)), ev.clientX, ev.clientY);
    }, { passive: false });
    var pointers = {}, last = null, pinch = null, startXY = null;
    svg.addEventListener('pointerdown', function (ev) {
      pointers[ev.pointerId] = ev; dragged = false; startXY = [ev.clientX, ev.clientY];
      var ids = Object.keys(pointers);
      if (ids.length === 2) {
        var a = pointers[ids[0]], b = pointers[ids[1]];
        pinch = { d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) };
      } else { last = [ev.clientX, ev.clientY]; }
    });
    svg.addEventListener('pointermove', function (ev) {
      if (!pointers[ev.pointerId]) return;
      pointers[ev.pointerId] = ev;
      var ids = Object.keys(pointers);
      if (ids.length === 2 && pinch) {
        var a = pointers[ids[0]], b = pointers[ids[1]], d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        if (d > 0) zoomAt(d / pinch.d, (a.clientX + b.clientX) / 2, (a.clientY + b.clientY) / 2);
        pinch.d = d; dragged = true; return;
      }
      if (!last || W / vb.w <= 1.01) return;
      if (Math.hypot(ev.clientX - startXY[0], ev.clientY - startXY[1]) > 4) {
        if (!dragged) svg.setPointerCapture(ev.pointerId);
        dragged = true;
      }
      if (!dragged) return;
      var r = svg.getBoundingClientRect();
      vb.x -= (ev.clientX - last[0]) / r.width * vb.w; vb.y -= (ev.clientY - last[1]) / r.height * vb.h;
      last = [ev.clientX, ev.clientY]; clamp(); redraw();
    });
    function up(ev) { delete pointers[ev.pointerId]; if (Object.keys(pointers).length < 2) pinch = null; last = null; }
    svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);
    svg.addEventListener('click', function (ev) { if (dragged) { ev.preventDefault(); ev.stopPropagation(); dragged = false; } }, true);
    frame.querySelectorAll('[data-zoom]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (b.dataset.zoom === 'in') zoomAt(1.8);
        else if (b.dataset.zoom === 'out') zoomAt(1 / 1.8);
        else { vb = { x: 0, y: 0, w: W, h: H }; redraw(); }
      });
    });
    // facility layers on and off
    var fig = frame.closest('figure') || document;
    fig.querySelectorAll('[data-fac-toggle]').forEach(function (cb) {
      cb.addEventListener('change', function () {
        var g = svg.querySelector('[data-fac="' + cb.dataset.facToggle + '"]');
        if (g) g.classList.toggle('hidden', !cb.checked);
      });
    });
    draw();
  });

  // "For you": suggestions from what the visitor told us, or (if they opted in) what they open. Everything is kept
  // in this browser's local storage under one key; nothing is sent anywhere. "Forget me" removes it.
  var KEY = 'ciynn-for-you', css = document.querySelector('link[href$="assets/style.css"]');
  var root = css ? css.getAttribute('href').replace('assets/style.css', '') : '';     // '' or '../' on sub-pages
  function loadPrefs() { try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch (e) { return null; } }
  function savePrefs(p) { try { localStorage.setItem(KEY, JSON.stringify(p)); return true; } catch (e) { return false; } }
  function forget() { try { localStorage.removeItem(KEY); } catch (e) {} }
  var prefs = loadPrefs();
  var NEAR = { uk: ['uk', 'online'], europe: ['uk', 'europe', 'online'], online: ['online'] };
  var ROLE_WORDS = { undergrad: /student|undergraduate|summer school|school on|graduate|careers?|ygn/i,
                     pgr: /phd|school|workshop|symposium|conference|student|early.career/i,
                     postdoc: /conference|symposium|workshop|fellowship|congress/i,
                     industry: /industry|supply chain|ygn|networking|nuclear institute|nia|professional/i,
                     staff: /conference|symposium|congress|workshop/i };

  // The learning model: online logistic regression, trained in this browser on what the visitor opens.
  // Features: the item's fields, kind, organiser, region and title words. An item they open is a positive example;
  // items they passed over just above it in the same list are (weaker) negative ones. Predictions are the
  // probability that they would open an item, and feed into the suggestion score.
  var STOP = /^(with|from|into|your|their|this|that|what|about|annual|international|conference|meeting|event|events|session|2026|2027|2028|part|online|webinar|series|introduction|intro)$/;
  function tokens(t) {
    return ((t || '').toLowerCase().match(/[a-z][a-z-]{3,}/g) || []).filter(function (w, i, all) {
      return !STOP.test(w) && all.indexOf(w) === i;
    }).slice(0, 12);
  }
  function feats(o) {
    var x = ['b'];
    (o.fields || []).forEach(function (f) { if (f) x.push('f:' + f); });
    if (o.kind) x.push('k:' + o.kind);
    if (o.org) x.push('o:' + o.org.split(' / ')[0]);
    if (o.region) x.push('r:' + o.region);
    tokens(o.title).forEach(function (w) { x.push('w:' + w); });
    return x.filter(function (f, i, all) { return all.indexOf(f) === i; });
  }
  function model() {
    prefs.model = prefs.model || { w: { b: -1 }, pos: 0, neg: 0 };    // starts believing most things won't interest them
    return prefs.model;
  }
  function predict(m, x) {
    var z = 0;
    x.forEach(function (f) { z += m.w[f] || 0; });
    return 1 / (1 + Math.exp(-z));
  }
  function learn(m, x, y, rate) {
    var g = (y - predict(m, x)) * rate / Math.sqrt(x.length);
    x.forEach(function (f) { m.w[f] = (m.w[f] || 0) * 0.999 + g; });   // small decay keeps old habits from dominating
    if (y) m.pos++; else m.neg++;
    var keys = Object.keys(m.w);
    if (keys.length > 600) {                                         // keep the model small
      keys.sort(function (a, b) { return Math.abs(m.w[b]) - Math.abs(m.w[a]); });
      keys.slice(600).forEach(function (k) { if (k !== 'b') delete m.w[k]; });
    }
  }
  function trained() { return prefs && prefs.learn && prefs.model && prefs.model.pos >= 2; }

  function score(item, p, fieldNames, now) {
    var why = [], s = 0, interests = p.interests || [], liked = false;
    item.fields.filter(function (f, i, all) { return all.indexOf(f) === i; }).forEach(function (f) {
      if (interests.indexOf(f) >= 0) { s += 3; why.push(fieldNames[f] || f); }
    });
    if (trained()) {
      var q = predict(p.model, feats(item));
      s += 6 * (q - 0.3);
      liked = q > 0.55;
      if (liked) why.push('like things you’ve opened');
    }
    if (s <= 0 && !liked && item.kind !== 'ours') return null;  // nothing in common: don't suggest it
    var near = NEAR[p.travel];
    if (near && near.indexOf(item.region) < 0) return null;     // somewhere they said they wouldn't go
    if (item.kind === 'ours') { s += 2; why.unshift('our own event'); }
    if (p.role && ROLE_WORDS[p.role] && ROLE_WORDS[p.role].test(item.title)) s += 1;
    if (item.start) {
      var days = (new Date(item.start) - now) / 864e5;
      if (days < -1 && item.kind !== 'news') return null;
      if (item.kind === 'news') s += days > -21 ? 0.5 : -1;
      else if (days < 45) { s += 1; why.push('coming up soon'); }
    }
    return { s: s, why: why };
  }

  // In plain words: what the model has learned so far (shown on the For you page)
  function describeModel(fieldNames) {
    if (!trained()) return '';
    var KINDS = { conference: 'conferences', event: 'events', opportunity: 'opportunities', news: 'news', ours: 'our own events' };
    var REG = { uk: 'the UK', europe: 'Europe', namerica: 'North America', world: 'further afield', online: 'online events' };
    var top = Object.keys(prefs.model.w).filter(function (k) { return k !== 'b' && prefs.model.w[k] > 0.15; })
      .sort(function (a, b) { return prefs.model.w[b] - prefs.model.w[a]; }).slice(0, 6).map(function (k) {
        var v = k.slice(2);
        return { f: fieldNames[v] ? fieldNames[v].toLowerCase() : v, k: KINDS[v] || v, o: v, r: REG[v] || v, w: '“' + v + '”' }[k[0]];
      });
    return top.length ? 'Learned so far from ' + prefs.model.pos + ' things you’ve opened: you lean towards ' + top.join(', ') + '.' : '';
  }

  function renderSuggestions(data) {
    var lists = document.querySelectorAll('[data-suggestions]');
    if (!lists.length) return;
    var ready = prefs && ((prefs.interests && prefs.interests.length) || trained());
    document.querySelectorAll('[data-foryou-invite]').forEach(function (el) { el.classList.toggle('hidden', !!ready); });
    lists.forEach(function (list) {
      list.textContent = '';
      if (!ready) {
        if (list.closest('[data-foryou-page]')) list.innerHTML = '<p class="empty">Choose a few interests above and we’ll suggest things here.</p>';
        return;
      }
      var learned = document.querySelector('[data-learned]');
      if (learned) learned.textContent = describeModel(data.fields);
      var now = new Date(), picks = [];
      data.items.forEach(function (it) { var r = score(it, prefs, data.fields, now); if (r) picks.push({ it: it, r: r }); });
      picks.sort(function (a, b) { return b.r.s - a.r.s || (a.it.start || '9').localeCompare(b.it.start || '9'); });
      picks = picks.slice(0, +list.dataset.limit || 10);
      if (!picks.length) {
        list.innerHTML = '<p class="empty">Nothing matches right now. Try adding an interest, or travelling a bit further.</p>';
        return;
      }
      var KIND = { ours: 'Our event', event: 'Event', conference: 'Conference', opportunity: 'Opportunity', news: 'News' };
      picks.forEach(function (p) {
        var it = p.it, a = document.createElement('article'), url = /^https?:/.test(it.url) ? it.url : root + it.url;
        a.className = 'row suggestion';
        var d = it.start ? new Date(it.start + 'T12:00:00') : null;
        var box = document.createElement('div'); box.className = 'date'; box.setAttribute('aria-hidden', 'true');
        box.innerHTML = d ? '<b></b><span></span>' : '<b>&middot;</b><span></span>';
        if (d) { box.querySelector('b').textContent = d.getDate(); box.querySelector('span').textContent = d.toLocaleString('en-GB', { month: 'short' }); }
        var body = document.createElement('div'), h = document.createElement('h3'), link = document.createElement('a');
        link.href = url; link.textContent = it.title; link.dataset.fields = it.fields.join(' ');
        link.dataset.kind = it.kind; link.dataset.org = it.org || ''; link.dataset.region = it.region || '';
        if (/^https?:/.test(it.url)) { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
        h.appendChild(link);
        var meta = document.createElement('div'); meta.className = 'meta';
        var kind = document.createElement('span'); kind.className = 'org'; kind.textContent = KIND[it.kind] || it.kind; meta.appendChild(kind);
        if (it.place) { var pl = document.createElement('span'); pl.textContent = it.place; meta.appendChild(pl); }
        if (p.r.why.length) { var w = document.createElement('span'); w.className = 'why'; w.textContent = 'Because: ' + p.r.why.slice(0, 2).join(', '); meta.appendChild(w); }
        body.appendChild(h); body.appendChild(meta);
        a.appendChild(box); a.appendChild(body); list.appendChild(a);
      });
    });
  }

  function markRows() {                          // "Suits you" on rows elsewhere on the site
    if (!prefs || !prefs.interests || !prefs.interests.length) return;
    document.querySelectorAll('.row[data-fields]').forEach(function (r) {
      var hit = r.dataset.fields.split(' ').some(function (f) { return prefs.interests.indexOf(f) >= 0; });
      if (hit && !r.querySelector('.suits')) {
        var m = document.createElement('span'); m.className = 'suits'; m.textContent = 'Suits you';
        var meta = r.querySelector('.meta'); if (meta) meta.insertBefore(m, meta.firstChild);
      }
    });
  }

  // learning (opt-in): what the visitor opens trains the model; what they passed over just above it counts against
  var PAGE_KIND = /conferences/.test(location.pathname) ? 'conference' : /opportunities/.test(location.pathname) ? 'opportunity'
    : /news/.test(location.pathname) ? 'news' : 'event';
  function rowItem(row, link) {
    link = link || row.querySelector('h3 a');
    var src = link && link.dataset.fields !== undefined ? link : row;
    var orgEl = row.querySelector('.org');
    return { title: link ? link.textContent : '', fields: (src.dataset.fields || '').split(' '),
             kind: (link && link.dataset.kind) || PAGE_KIND,
             org: (link && link.dataset.org) || (orgEl && !row.classList.contains('suggestion') ? orgEl.textContent : ''),
             region: (link && link.dataset.region) || row.dataset.region || '' };
  }
  document.addEventListener('click', function (ev) {
    if (!prefs || !prefs.learn) return;
    var a = ev.target.closest && ev.target.closest('a');
    var row = a && a.closest('.row');
    if (!row || !(a.dataset.fields !== undefined || row.dataset.fields !== undefined)) return;
    var m = model();
    learn(m, feats(rowItem(row, a)), 1, 0.8);
    var rows = Array.prototype.slice.call(row.parentNode.querySelectorAll(':scope > .row:not(.hidden)'));
    rows.slice(Math.max(0, rows.indexOf(row) - 3), rows.indexOf(row)).forEach(function (r) {   // passed over
      learn(m, feats(rowItem(r)), 0, 0.25);
    });
    savePrefs(prefs);
  }, true);

  // the For you page: the settings form
  var form = document.querySelector('[data-prefs]');
  if (form) {
    var fld = function (n) { return form.querySelector('[name="' + n + '"]'); };
    if (prefs) {
      (prefs.interests || []).forEach(function (v) { var c = form.querySelector('input[name="interest"][value="' + v + '"]'); if (c) c.checked = true; });
      if (prefs.role) fld('role').value = prefs.role;
      if (prefs.travel) fld('travel').value = prefs.travel;
      fld('learn').checked = !!prefs.learn;
    }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var p = { v: 1, interests: Array.prototype.map.call(form.querySelectorAll('input[name="interest"]:checked'), function (c) { return c.value; }),
                role: fld('role').value, travel: fld('travel').value, learn: fld('learn').checked,
                model: fld('learn').checked && prefs && prefs.model ? prefs.model : undefined };
      var ok = savePrefs(p); prefs = p;
      var msg = form.querySelector('[data-saved]');
      msg.textContent = ok ? 'Saved in this browser.' : 'This browser won’t let the site save anything (private mode?), so your choices last only until you leave the page.';
      msg.classList.remove('hidden');
      if (window.__forYouData) renderSuggestions(window.__forYouData);
    });
    form.querySelector('[data-forget]').addEventListener('click', function () {
      forget(); prefs = null; form.reset();
      var msg = form.querySelector('[data-saved]'); msg.textContent = 'Forgotten: nothing about you is stored in this browser now.'; msg.classList.remove('hidden');
      if (window.__forYouData) renderSuggestions(window.__forYouData);
    });
  }

  if (document.querySelector('[data-suggestions]')) {
    fetch(root + 'items.json').then(function (r) { return r.json(); }).then(function (data) {
      window.__forYouData = data; renderSuggestions(data);
    }).catch(function () {});
  }
  markRows();

  // Copy buttons next to an address shown as text
  document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      var text = b.dataset.copy, done = function () { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1800); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {});
    });
  });
})();
