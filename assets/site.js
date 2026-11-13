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

  // Copy buttons next to an address shown as text
  document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      var text = b.dataset.copy, done = function () { b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1800); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {});
    });
  });
})();
