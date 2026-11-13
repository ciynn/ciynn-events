// Members' area: accounts (Supabase Auth), profile, For you, member exclusives, directory and account controls.
// Passwords never touch this website: Supabase checks them and keeps only salted hashes. Every query runs with
// the member's own session, and the database's row-level security decides what they may see (supabase/schema.sql).
(function () {
  'use strict';
  var box = document.querySelector('[data-members]');
  if (!box || !window.supabase) return;
  var sb = window.supabase.createClient(box.dataset.url, box.dataset.key, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: 'pkce' }
  });
  var $ = function (sel, el) { return (el || box).querySelector(sel); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || box).querySelectorAll(sel)); };
  var KEY = 'ciynn-for-you';
  var ROLE = { undergraduate: 'undergrad', msc: 'undergrad', pgr: 'pgr', postdoc: 'postdoc', staff: 'staff', industry: 'industry' };
  var profile = null, user = null;

  function say(el, text, bad) { el.textContent = text; el.classList.toggle('bad', !!bad); el.classList.remove('hidden'); }
  function show(state) { $$('[data-state]').forEach(function (s) { s.classList.toggle('hidden', s.dataset.state !== state); }); }
  function local() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
  function setLocal(p) { try { localStorage.setItem(KEY, JSON.stringify(p)); } catch (e) {} }
  function friendly(err) {
    var m = (err && err.message) || String(err);
    if (/Invalid login/i.test(m)) return 'That email and password don’t match an account. Check them, or reset your password.';
    if (/Email not confirmed/i.test(m)) return 'Please confirm your email first: open the link we sent you.';
    if (/rate limit|too many/i.test(m)) return 'Too many attempts. Please wait a few minutes and try again.';
    if (/password/i.test(m) && /characters|weak|short/i.test(m)) return 'Choose a longer password: at least 10 characters.';
    if (/already registered|already been registered/i.test(m)) return 'There’s already an account with that email. Sign in, or reset your password.';
    return m;
  }

  // ---------------------------------------------------------------- tabs (sign in / create account, member sections)
  $$('[data-tab]').forEach(function (t) {
    t.addEventListener('click', function () {
      var group = t.closest('[data-tabs]');
      $$('[data-tab]', group).forEach(function (x) { x.setAttribute('aria-selected', String(x === t)); });
      $$('[data-panel]', group.parentNode).forEach(function (p) { p.classList.toggle('hidden', p.dataset.panel !== t.dataset.tab); });
      if (t.dataset.tab === 'exclusives') loadExclusives();
      if (t.dataset.tab === 'directory') loadDirectory();
    });
  });
  if (location.hash === '#create') { var c = $('[data-tab="create"]'); if (c) c.click(); }

  // ---------------------------------------------------------------- sign in, create account, reset password
  $('[data-signin]').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target, msg = $('[data-msg]', f);
    sb.auth.signInWithPassword({ email: f.email.value.trim(), password: f.password.value }).then(function (r) {
      if (r.error) say(msg, friendly(r.error), true);
    });
  });
  var uname = $('[data-create] [name="username"]'), unameMsg = $('[data-username-msg]');
  uname.addEventListener('change', function () {
    var v = uname.value.trim();
    if (!/^[A-Za-z0-9_.-]{3,30}$/.test(v)) { say(unameMsg, '3 to 30 letters, numbers, dots, dashes or underscores.', true); return; }
    sb.rpc('username_available', { name: v }).then(function (r) {
      if (!r.error) say(unameMsg, r.data ? 'That username is free.' : 'That username is taken.', !r.data);
    });
  });
  $('[data-create]').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target, msg = $('[data-msg]', f);
    if (f.password.value !== f.password2.value) { say(msg, 'The two passwords don’t match.', true); return; }
    if (f.password.value.length < 10) { say(msg, 'Choose a password of at least 10 characters.', true); return; }
    if (!/^[A-Za-z0-9_.-]{3,30}$/.test(f.username.value.trim())) { say(msg, 'Usernames are 3 to 30 letters, numbers, dots, dashes or underscores.', true); return; }
    if (!f.agree.checked) { say(msg, 'Please agree to the privacy notice to create an account.', true); return; }
    sb.rpc('username_available', { name: f.username.value.trim() }).then(function (r) {
      if (r.data === false) { say(msg, 'That username is taken. Try another.', true); return; }
      return sb.auth.signUp({
        email: f.email.value.trim(), password: f.password.value,
        options: { data: { username: f.username.value.trim(), full_name: f.full_name.value.trim() },
                   emailRedirectTo: location.origin + location.pathname }
      }).then(function (r2) {
        if (r2.error) say(msg, friendly(r2.error), true);
        else { f.reset(); say(msg, 'Nearly there: we’ve emailed you a link. Open it to confirm your email, then sign in.'); }
      });
    });
  });
  $('[data-forgot]').addEventListener('click', function () {
    var f = $('[data-signin]'), msg = $('[data-msg]', f), email = f.email.value.trim();
    if (!email) { say(msg, 'Type your email above first, then choose “Forgotten your password?” again.', true); return; }
    sb.auth.resetPasswordForEmail(email, { redirectTo: location.origin + location.pathname }).then(function () {
      say(msg, 'If there’s an account for that email, we’ve sent a link to choose a new password.');
    });
  });
  $('[data-newpass]').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target, msg = $('[data-msg]', f);
    if (f.password.value.length < 10) { say(msg, 'Choose a password of at least 10 characters.', true); return; }
    sb.auth.updateUser({ password: f.password.value }).then(function (r) {
      if (r.error) say(msg, friendly(r.error), true); else { say(msg, 'Password changed.'); setTimeout(function () { start(); }, 900); }
    });
  });

  // ---------------------------------------------------------------- the signed-in area
  var PF = $('[data-profile]');
  function fill(p) {
    $$('input, select, textarea', PF).forEach(function (el) {
      var v = p[el.name];
      if (el.type === 'checkbox' && el.dataset.list !== undefined) el.checked = (v || []).indexOf(el.value) >= 0;
      else if (el.type === 'checkbox') el.checked = !!v;
      else if (Array.isArray(v)) el.value = v.join(', ');
      else el.value = v == null ? '' : v;
    });
    $('[data-hello]').textContent = p.full_name ? p.full_name.split(' ')[0] : p.username;
    toggleNeeds();
  }
  function collect() {
    var out = {}, lists = {};
    $$('input, select, textarea', PF).forEach(function (el) {
      if (!el.name) return;
      if (el.type === 'checkbox' && el.dataset.list !== undefined) { (lists[el.name] = lists[el.name] || []); if (el.checked) lists[el.name].push(el.value); }
      else if (el.type === 'checkbox') out[el.name] = el.checked;
      else if (el.dataset.csv !== undefined) out[el.name] = el.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean).slice(0, 30);
      else out[el.name] = el.value.trim() === '' ? null : el.value.trim();
    });
    Object.keys(lists).forEach(function (k) { out[k] = lists[k]; });
    if (!out.needs_consent) { out.dietary = null; out.accessibility = null; }
    if (!out.full_name) out.full_name = profile.full_name;
    delete out.username;                                       // usernames are fixed once chosen
    return out;
  }
  function toggleNeeds() {
    var on = $('[name="needs_consent"]', PF).checked;
    $$('[data-needs]', PF).forEach(function (el) { el.disabled = !on; if (!on) el.value = ''; });
  }
  $('[name="needs_consent"]', PF).addEventListener('change', toggleNeeds);

  function syncForYou(p) {                                    // the profile's choices drive suggestions site-wide
    var l = local();
    var model = (p.for_you && p.for_you.model) || l.model;
    var merged = { v: 1, interests: p.interests || [], travel: p.travel || 'anywhere', role: ROLE[p.status] || '',
                   learn: p.for_you && p.for_you.learn !== undefined ? p.for_you.learn : !!l.learn, model: model };
    setLocal(merged);
    return merged;
  }
  function saveForYou() {                                     // and what the browser has learned goes back to the profile
    if (!user) return Promise.resolve();
    var l = local();
    return sb.from('profiles').update({ for_you: { learn: !!l.learn, model: l.model || null } }).eq('id', user.id);
  }

  PF.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var msg = $('[data-msg]', PF), data = collect();
    data.for_you = { learn: $('[name="learn_toggle"]', PF).checked, model: local().model || null };
    delete data.learn_toggle;
    sb.from('profiles').update(data).eq('id', user.id).select().single().then(function (r) {
      if (r.error) { say(msg, 'Couldn’t save: ' + friendly(r.error), true); return; }
      profile = r.data; syncForYou(profile); say(msg, 'Saved.');
    });
  });

  function loadExclusives() {
    var list = $('[data-exclusives]');
    sb.from('exclusives').select('*').order('published_at', { ascending: false }).then(function (r) {
      list.textContent = '';
      if (r.error || !r.data.length) { list.innerHTML = '<p class="empty">Nothing here yet. Member exclusives (recordings, slides, early places and offers) will appear here.</p>'; return; }
      r.data.forEach(function (x) {
        var a = document.createElement('article'); a.className = 'paper';
        var tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = x.kind; a.appendChild(tag);
        var h = document.createElement('h3'); h.textContent = x.title; a.appendChild(h);
        if (x.summary) { var s = document.createElement('p'); s.className = 'muted'; s.textContent = x.summary; a.appendChild(s); }
        if (x.body) { var b = document.createElement('p'); b.textContent = x.body; a.appendChild(b); }
        var go = document.createElement('p');
        if (x.link && /^https:\/\//.test(x.link)) {
          var l = document.createElement('a'); l.href = x.link; l.target = '_blank'; l.rel = 'noopener noreferrer'; l.textContent = 'Open'; go.appendChild(l);
        } else if (x.file_path) {
          var btn = document.createElement('button'); btn.type = 'button'; btn.className = 'btn btn-line'; btn.textContent = 'Download';
          btn.addEventListener('click', function () {
            sb.storage.from('exclusives').createSignedUrl(x.file_path, 300).then(function (u) { if (u.data) window.open(u.data.signedUrl, '_blank', 'noopener'); });
          });
          go.appendChild(btn);
        }
        a.appendChild(go); list.appendChild(a);
      });
    });
  }

  var dirData = [];
  function loadDirectory() {
    if (dirData.length) return;
    sb.from('directory').select('*').order('full_name').then(function (r) { dirData = r.data || []; drawDirectory(); });
  }
  function drawDirectory() {
    var list = $('[data-directory]'), q = ($('[data-dir-search]').value || '').toLowerCase();
    var STATUS = { undergraduate: 'Undergraduate', msc: 'MSc student', pgr: 'PhD student', postdoc: 'Postdoc', staff: 'Staff', industry: 'Industry', other: '' };
    var MENTOR = { want: 'Would like a mentor', offer: 'Happy to mentor', both: 'Would like a mentor and happy to mentor' };
    list.textContent = '';
    var shown = dirData.filter(function (m) { return !q || JSON.stringify(m).toLowerCase().indexOf(q) >= 0; });
    if (!shown.length) { list.innerHTML = '<p class="empty">No one to show yet. Members appear here once they choose to be listed in their profile.</p>'; return; }
    shown.forEach(function (m) {
      var li = document.createElement('li');
      var h = document.createElement('h3'); h.textContent = m.full_name + (m.pronouns ? ' (' + m.pronouns + ')' : ''); li.appendChild(h);
      var role = document.createElement('p'); role.className = 'role';
      role.textContent = [STATUS[m.status], m.department || m.organisation].filter(Boolean).join(', '); li.appendChild(role);
      if (m.research_area) { var ra = document.createElement('p'); ra.textContent = m.research_area; li.appendChild(ra); }
      if (m.skills && m.skills.length) { var sk = document.createElement('p'); sk.className = 'small muted'; sk.textContent = 'Skills: ' + m.skills.join(', '); li.appendChild(sk); }
      if (MENTOR[m.mentoring]) { var me = document.createElement('p'); me.className = 'small'; me.textContent = MENTOR[m.mentoring]; li.appendChild(me); }
      var links = document.createElement('p'); links.className = 'small';
      if (m.linkedin && /^https:\/\/([a-z]+\.)?linkedin\.com\//.test(m.linkedin)) { var a = document.createElement('a'); a.href = m.linkedin; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = 'LinkedIn'; links.appendChild(a); }
      if (m.orcid) { var o = document.createElement('a'); o.href = 'https://orcid.org/' + m.orcid; o.target = '_blank'; o.rel = 'noopener noreferrer'; o.textContent = ' ORCID'; links.appendChild(o); }
      li.appendChild(links); list.appendChild(li);
    });
  }
  $('[data-dir-search]').addEventListener('input', drawDirectory);

  // account: download my data, change email, sign out, delete
  $('[data-download]').addEventListener('click', function () {
    var blob = new Blob([JSON.stringify({ account: { email: user.email, created: user.created_at }, profile: profile }, null, 2)], { type: 'application/json' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'my-ciynn-data.json'; a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
  });
  $('[data-email-change]').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target, msg = $('[data-msg]', f);
    sb.auth.updateUser({ email: f.email.value.trim() }, { emailRedirectTo: location.origin + location.pathname }).then(function (r) {
      say(msg, r.error ? friendly(r.error) : 'Check both inboxes: we’ve sent links to confirm the change.', !!r.error);
    });
  });
  $('[data-pass-change]').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target, msg = $('[data-msg]', f);
    if (f.password.value.length < 10) { say(msg, 'Choose a password of at least 10 characters.', true); return; }
    sb.auth.updateUser({ password: f.password.value }).then(function (r) { f.reset(); say(msg, r.error ? friendly(r.error) : 'Password changed.', !!r.error); });
  });
  $$('[data-signout]').forEach(function (b) {
    b.addEventListener('click', function () { saveForYou().then(function () { return sb.auth.signOut(); }); });
  });
  $('[data-delete]').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var f = ev.target, msg = $('[data-msg]', f);
    if (f.confirm.value.trim().toLowerCase() !== String(profile.username).toLowerCase()) { say(msg, 'Type your username exactly to confirm.', true); return; }
    sb.rpc('delete_my_account').then(function (r) {
      if (r.error) { say(msg, friendly(r.error), true); return; }
      try { localStorage.removeItem(KEY); } catch (e) {}
      sb.auth.signOut().then(function () { show('out'); say($('[data-out-msg]'), 'Your account and everything in it have been deleted.'); });
    });
  });

  // ---------------------------------------------------------------- start
  function start() {
    sb.auth.getSession().then(function (r) {
      var s = r.data && r.data.session;
      if (!s) { user = null; profile = null; show('out'); return; }
      user = s.user;
      sb.from('profiles').select('*').eq('id', user.id).single().then(function (p) {
        if (p.error) { show('out'); say($('[data-out-msg]'), 'Signed in, but your profile couldn’t be loaded. Please try again shortly.', true); return; }
        profile = p.data; fill(profile);
        var merged = syncForYou(profile);
        $('[name="learn_toggle"]', PF).checked = !!merged.learn;
        $('[data-email-now]').textContent = user.email;
        show('in');
        saveForYou();
      });
    });
  }
  sb.auth.onAuthStateChange(function (event) {
    if (event === 'PASSWORD_RECOVERY') { show('recover'); return; }
    if (event === 'SIGNED_IN' || event === 'SIGNED_OUT' || event === 'USER_UPDATED') start();
  });
  window.addEventListener('pagehide', saveForYou);
  start();
})();
