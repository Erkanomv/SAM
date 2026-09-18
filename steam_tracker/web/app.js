(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const state = { accounts: [], version: '0.5.0', apiKeyConfigured: false, dataModeText: 'Public Steam data', steamInstalled: true, bulkLoginActive: false };
  const ui = {
    filter: localStorage.getItem('sam.filter') || 'ALL',
    sort: localStorage.getItem('sam.sort') || 'Favorite',
    query: '',
    busy: false,
  };
  let bulk = null;
  let modalKind = '';

  const icons = {
    heart: '<svg viewBox="0 0 24 24"><path d="M20.8 4.6a5.4 5.4 0 0 0-7.6 0L12 5.8l-1.2-1.2a5.4 5.4 0 0 0-7.6 7.6l1.2 1.2L12 21l7.6-7.6 1.2-1.2a5.4 5.4 0 0 0 0-7.6z"/></svg>',
    more: '<svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/></svg>',
    clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.8 1.8"/></svg>',
    chev: '<svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>',
  };

  const esc = v => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const safeUrl = v => /^https:\/\//i.test(String(v || '')) ? String(v).replace(/"/g, '%22') : '';
  const fmtHours = v => {
    const n = Number(v || 0);
    if (!n) return '—';
    if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k h`;
    return `${n >= 100 ? Math.round(n) : n.toFixed(1)} h`;
  };
  const isVcbnd = a => Number(a.vcbndUntil || 0) > Date.now() / 1000;
  const accountStatus = a => a.comp ? 'COMP' : (isVcbnd(a) ? 'VCBND' : 'UNBND');

  function remaining(until) {
    let s = Math.max(0, Math.floor(Number(until || 0) - Date.now() / 1000));
    if (!s) return '';
    const d = Math.floor(s / 86400); s %= 86400;
    const h = Math.floor(s / 3600); s %= 3600;
    const m = Math.floor(s / 60);
    if (d) return `${d}d ${h}h ${m}m`;
    if (h) return `${h}h ${m}m`;
    return `${m}m`;
  }

  async function native(method, ...args) {
    if (!window.pywebview?.api?.[method]) throw new Error(`Native API unavailable: ${method}`);
    return await window.pywebview.api[method](...args);
  }

  function setBusy(v) {
    ui.busy = !!v;
    document.body.classList.toggle('busy', ui.busy);
  }

  function toast(message, kind = 'info') {
    if (!message) return;
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.textContent = message;
    $('#toast-stack').appendChild(el);
    setTimeout(() => el.remove(), 3500);
  }

  async function run(fn, say = true) {
    if (ui.busy) return null;
    setBusy(true);
    try {
      const result = await fn();
      if (result?.state) applyState(result.state);
      if (say && result?.message) toast(result.message, result.ok === false ? 'error' : 'success');
      return result;
    } catch (e) {
      toast(e?.message || String(e), 'error');
      return null;
    } finally {
      setBusy(false);
    }
  }

  function cardHtml(a) {
    const st = accountStatus(a);
    const vcb = isVcbnd(a);
    const games = Array.isArray(a.topGames) ? a.topGames : [];
    const top = games[0] || {};
    const hero = safeUrl(top.header_url);
    const avatar = safeUrl(a.avatarUrl);
    const mini = games.slice(0, 5).map(g => safeUrl(g.icon_url)).filter(Boolean).map(src => `<img class="mini-icon" src="${src}" loading="lazy" decoding="async">`).join('');
    const strip = games.slice(0, 7).map(g => safeUrl(g.header_url || g.icon_url)).filter(Boolean).map(src => `<img class="game-thumb" src="${src}" loading="lazy" decoding="async">`).join('');
    const loginReady = !!a.loginUsername && !!a.hasPassword;

    return `
      <article class="account-card" data-steam-id="${esc(a.steamId)}">
        <div class="card-hero">
          ${hero ? `<img class="card-hero-art" src="${hero}" loading="lazy" decoding="async">` : ''}
          <div class="card-hero-content">
            <div class="game-badge">${hero ? `<img src="${hero}" alt="">` : ''}</div>
            <div class="hero-copy">
              <div class="hero-title">${esc(a.topGameName || 'STEAM')}</div>
              <div class="hero-meta">${fmtHours(a.topGameHours)} · MOST PLAYED</div>
            </div>
            <button class="favorite-btn ${a.favorite ? 'active' : ''}" data-action="favorite" aria-label="Favorite account">${icons.heart}</button>
          </div>
        </div>

        <div class="card-body">
          <div class="profile-row">
            <div class="avatar-wrap">${avatar ? `<img src="${avatar}" alt="" loading="lazy">` : ''}</div>
            <div class="account-copy">
              <div class="account-name">${esc(a.personaName || a.steamId)}</div>
              <div class="account-subline"><span class="presence-dot ${Number(a.personaState) > 0 ? 'online' : ''}"></span>${Number(a.personaState) > 0 ? 'Online' : 'Offline'}</div>
              <div class="mini-icons">${mini}</div>
            </div>
            <div class="account-level">${Number(a.steamLevel) >= 0 ? `LVL ${a.steamLevel}` : 'LVL —'}</div>
          </div>

          <div class="stats-row">
            <div class="stat-box"><span class="stat-label">HOURS · ${esc((a.topGameName || 'TOP GAME').toUpperCase().slice(0, 18))}</span><strong class="stat-value">${fmtHours(a.topGameHours)}</strong></div>
            <div class="stat-box"><span class="stat-label">TOTAL PLAYTIME</span><strong class="stat-value">${fmtHours(a.totalHours)}</strong></div>
          </div>

          <div class="status-row" data-timer-until="${Number(a.vcbndUntil || 0)}" data-comp="${a.comp ? '1' : '0'}">
            <span class="status-label">${st === 'VCBND' ? 'VCBND TIMER' : 'ACCOUNT STATUS'}</span>
            <span class="status-remaining">${st === 'VCBND' ? remaining(a.vcbndUntil) : ''}</span>
            <strong class="status-value ${st.toLowerCase()}">${st}</strong>
          </div>

          <div class="library-block">
            <div class="library-head">LIBRARY <span class="library-count">${Number(a.gameCount || 0).toLocaleString()}</span>${icons.chev}</div>
            <div class="game-strip">${strip}</div>
          </div>

          <div class="card-actions">
            <button class="card-menu-btn" data-action="menu" aria-label="More actions">${icons.more}</button>
            <button class="timer-btn ${vcb ? 'active' : ''}" data-action="timer">${icons.clock}<span>${vcb ? remaining(a.vcbndUntil) : 'Set timer'}</span></button>
            <button class="comp-btn ${a.comp ? 'active' : ''}" data-action="comp" aria-pressed="${a.comp ? 'true' : 'false'}">COMP</button>
            <button class="login-btn" data-action="login">${loginReady ? 'LOGIN' : 'SET LOGIN'}</button>
          </div>
        </div>
      </article>`;
  }

  function visibleAccounts() {
    const q = ui.query.trim().toLowerCase();
    let items = state.accounts.filter(a => {
      if (ui.filter !== 'ALL' && accountStatus(a) !== ui.filter) return false;
      if (q) {
        const hay = `${a.personaName || ''} ${a.steamId || ''} ${a.loginUsername || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    return [...items].sort((a, b) => {
      if (ui.sort === 'Playtime') return Number(b.totalHours || 0) - Number(a.totalHours || 0);
      if (ui.sort === 'Timer') return (isVcbnd(a) ? Number(a.vcbndUntil) : Number.MAX_SAFE_INTEGER) - (isVcbnd(b) ? Number(b.vcbndUntil) : Number.MAX_SAFE_INTEGER);
      if (ui.sort === 'Name') return String(a.personaName || '').localeCompare(String(b.personaName || ''), undefined, { sensitivity: 'base' });
      if (ui.sort === 'Date added') return Number(b.dateAdded || 0) - Number(a.dateAdded || 0);
      if (!!a.favorite !== !!b.favorite) return a.favorite ? -1 : 1;
      return String(a.personaName || '').localeCompare(String(b.personaName || ''), undefined, { sensitivity: 'base' });
    });
  }

  function render() {
    const all = state.accounts.length;
    const comp = state.accounts.filter(a => accountStatus(a) === 'COMP').length;
    const vcb = state.accounts.filter(a => accountStatus(a) === 'VCBND').length;
    const unb = state.accounts.filter(a => accountStatus(a) === 'UNBND').length;
    const shown = visibleAccounts();

    $('#all-count').textContent = all;
    $('#unbnd-count').textContent = unb;
    $('#vcbnd-count').textContent = vcb;
    $('#comp-count').textContent = comp;
    $('#shown-count').textContent = `${shown.length} shown`;
    $('#account-summary').textContent = all ? `${all} linked account${all === 1 ? '' : 's'}` : 'No accounts linked';
    $('#connection-text').textContent = state.dataModeText || 'Public Steam data';
    $('#connection-pill').classList.toggle('public', !state.apiKeyConfigured);
    $('#bulk-login-btn').classList.toggle('queue-active', !!state.bulkLoginActive);
    $('#sort-select').value = ui.sort;
    $$('.filter-chip').forEach(b => b.classList.toggle('active', b.dataset.filter === ui.filter));
    $('#account-grid').innerHTML = shown.map(cardHtml).join('');

    const empty = $('#empty-state');
    if (!shown.length) {
      empty.classList.remove('hidden');
      if (all) {
        $('#empty-title').textContent = 'Nothing matches';
        $('#empty-copy').textContent = 'Try another search or account status filter.';
        $('#empty-add-btn').classList.add('hidden');
      } else {
        $('#empty-title').textContent = 'No accounts yet';
        $('#empty-copy').textContent = 'Link a Steam account to start building your library.';
        $('#empty-add-btn').classList.remove('hidden');
      }
    } else empty.classList.add('hidden');
  }

  function applyState(next) {
    if (!next || typeof next !== 'object') return;
    Object.assign(state, next);
    render();
  }

  function accountByCard(card) {
    return state.accounts.find(a => String(a.steamId) === String(card?.dataset?.steamId));
  }

  function hideFloating() {
    $('#popover').classList.add('hidden');
    $('#context-menu').classList.add('hidden');
  }

  function placeFloating(el, anchor, width) {
    const r = anchor.getBoundingClientRect();
    const left = Math.min(innerWidth - width - 10, Math.max(10, r.right - width));
    el.style.left = `${left}px`;
    el.style.top = `${Math.min(innerHeight - 210, r.bottom + 7)}px`;
  }

  function showTimer(a, anchor) {
    const pop = $('#popover');
    pop.innerHTML = `
      <div class="popover-title">${isVcbnd(a) ? 'Update VCBND timer' : 'Set VCBND timer'}</div>
      <p class="popover-copy">Enter any number of days. Decimal values work too.</p>
      <div class="timer-entry"><input id="timer-days" inputmode="decimal" placeholder="Days, e.g. 7"><button id="apply-timer">Set</button></div>
      ${isVcbnd(a) ? '<div class="popover-actions"><button class="popover-clear" id="clear-timer">Clear timer</button></div>' : ''}`;
    pop.dataset.steamId = a.steamId;
    pop.classList.remove('hidden');
    requestAnimationFrame(() => {
      placeFloating(pop, anchor, 250);
      $('#timer-days')?.focus();
    });
  }

  function showMenu(a, anchor) {
    const menu = $('#context-menu');
    menu.dataset.steamId = a.steamId;
    menu.innerHTML = `
      <button class="menu-item" data-menu="credentials">Edit login</button>
      <button class="menu-item" data-menu="refresh">Refresh account</button>
      <button class="menu-item" data-menu="profile">Open Steam profile</button>
      <button class="menu-item" data-menu="copy">Copy SteamID</button>
      <button class="menu-item" data-menu="favorite">${a.favorite ? 'Unfavorite' : 'Favorite'}</button>
      <button class="menu-item" data-menu="comp">${a.comp ? 'Clear COMP' : 'Mark as COMP'}</button>
      <div class="menu-separator"></div>
      <button class="menu-item danger" data-menu="delete">Remove account</button>`;
    menu.classList.remove('hidden');
    requestAnimationFrame(() => placeFloating(menu, anchor, 196));
  }

  function openModal(html, kind = '') {
    modalKind = kind;
    $('#modal-sheet').innerHTML = html;
    $('#modal-layer').classList.remove('hidden');
    $('#modal-layer').setAttribute('aria-hidden', 'false');
  }

  function closeModal() {
    modalKind = '';
    $('#modal-layer').classList.add('hidden');
    $('#modal-layer').setAttribute('aria-hidden', 'true');
    $('#modal-sheet').innerHTML = '';
  }

  const modalHead = title => `<header class="sheet-head"><div><div class="sheet-kicker">SAM</div><div class="sheet-title">${esc(title)}</div></div><button class="sheet-close" data-close-modal>×</button></header>`;

  function openCredentials(a) {
    openModal(`${modalHead('Login credentials')}<div class="sheet-body">
      <section class="settings-section"><h3 class="section-label">${esc(a.personaName)}</h3><p class="section-copy">Enter the real Steam login/account name. The password can be stored in Windows Credential Manager.</p>
      <div class="field"><label>Steam account name</label><input id="credential-user" value="${esc(a.loginUsername || '')}"></div>
      <div class="field"><label>Password</label><input id="credential-pass" type="password" placeholder="${a.hasPassword ? 'Stored password — type to replace it' : 'Enter password'}"></div>
      <label class="section-copy"><input id="credential-store" type="checkbox" ${a.hasPassword ? 'checked' : ''}> Store password securely</label>
      <div class="button-row" style="margin-top:14px"><button class="btn primary" id="save-credentials" data-steam-id="${esc(a.steamId)}">Save login</button>${a.hasPassword ? `<button class="btn danger" id="forget-password" data-steam-id="${esc(a.steamId)}">Forget password</button>` : ''}</div>
      </section></div>`, 'credentials');
  }

  function openSettings() {
    openModal(`${modalHead('Settings')}<div class="sheet-body">
      <section class="settings-section"><h3 class="section-label">Steam data</h3><p class="section-copy">The API key is optional. Public Steam data still works without one.</p>
      <div class="field"><label>Steam Web API key</label><input id="api-key-input" type="password" placeholder="32-character API key"></div>
      <div class="button-row"><button class="btn primary" id="save-api-key">Validate & save</button><button class="btn" id="open-api-page">Get API key</button>${state.apiKeyConfigured ? '<button class="btn danger" id="clear-api-key">Remove key</button>' : ''}</div></section>
      <section class="settings-section"><h3 class="section-label">Build</h3><p class="section-copy">SAM v${esc(state.version)} · WebView2 frontend · local SQLite cache.</p></section>
    </div>`, 'settings');
  }

  function renderBulkModal() {
    if (modalKind !== 'bulk') return;
    const b = bulk || { phase: 'idle', active: false, total: 0, success: 0, failed: 0, results: [], selection: null };
    const sel = b.selection;
    const results = Array.isArray(b.results) ? b.results : [];
    const rows = results.map(r => `<div class="bulk-row"><span class="bulk-user">${esc(r.username)}</span><small>${esc((r.message || '').slice(0, 80))}</small><span class="bulk-state">${esc((r.status || 'pending').toUpperCase())}</span></div>`).join('');
    openModal(`${modalHead('Bulk login')}<div class="sheet-body">
      <section class="settings-section"><h3 class="section-label">Sequential Steam login</h3><p class="section-copy">Choose a .txt with one <code>User:Password</code> per line. Steam is switched one account at a time.</p>
      ${sel ? `<p class="section-copy"><strong>${esc(sel.filename)}</strong> · ${sel.count} accounts</p>` : ''}
      <div class="button-row"><button class="btn" id="choose-bulk-file">Choose .txt</button>${sel && !b.active ? '<button class="btn primary" id="start-bulk">Start queue</button>' : ''}${b.active ? '<button class="btn danger" id="cancel-bulk">Stop queue</button>' : ''}</div></section>
      <section class="settings-section"><h3 class="section-label">${b.active ? 'Queue running' : 'Queue'}</h3><p class="section-copy">${Number(b.success || 0)} added · ${Number(b.failed || 0)} failed · ${Number(b.total || 0)} total</p><div class="bulk-list">${rows || '<p class="section-copy">No file selected yet.</p>'}</div></section>
    </div>`, 'bulk');
  }

  async function openBulk() {
    openModal(`${modalHead('Bulk login')}<div class="sheet-body"><p class="section-copy">Loading queue…</p></div>`, 'bulk');
    try {
      bulk = await native('get_bulk_login_status');
      renderBulkModal();
    } catch (e) {
      toast(e.message, 'error');
      closeModal();
    }
  }

  document.addEventListener('click', async e => {
    const filter = e.target.closest('.filter-chip');
    if (filter) {
      ui.filter = filter.dataset.filter;
      localStorage.setItem('sam.filter', ui.filter);
      render();
      return;
    }

    const card = e.target.closest('.account-card');
    const action = e.target.closest('[data-action]');
    if (card && action) {
      const a = accountByCard(card);
      if (!a) return;
      if (action.dataset.action === 'favorite') await run(() => native('toggle_favorite', a.steamId), false);
      if (action.dataset.action === 'comp') await run(() => native('toggle_comp', a.steamId));
      if (action.dataset.action === 'timer') showTimer(a, action);
      if (action.dataset.action === 'menu') showMenu(a, action);
      if (action.dataset.action === 'login') {
        if (!a.loginUsername || !a.hasPassword) openCredentials(a);
        else {
          const r = await run(() => native('login_account', a.steamId));
          if (r?.needsCredentials) openCredentials(a);
        }
      }
      return;
    }

    if (e.target.closest('#add-account-btn,#empty-add-btn')) { await run(() => native('add_account')); return; }
    if (e.target.closest('#refresh-all-btn')) { await run(() => native('refresh_all')); return; }
    if (e.target.closest('#settings-btn')) { openSettings(); return; }
    if (e.target.closest('#bulk-login-btn')) { await openBulk(); return; }
    if (e.target.closest('[data-close-modal]')) { closeModal(); return; }

    if (e.target.closest('#apply-timer')) {
      const sid = $('#popover').dataset.steamId;
      const days = $('#timer-days').value;
      const r = await run(() => native('set_timer', sid, days));
      if (r?.ok) hideFloating();
      return;
    }
    if (e.target.closest('#clear-timer')) {
      const sid = $('#popover').dataset.steamId;
      const r = await run(() => native('clear_timer', sid));
      if (r?.ok) hideFloating();
      return;
    }

    const menuItem = e.target.closest('[data-menu]');
    if (menuItem) {
      const sid = $('#context-menu').dataset.steamId;
      const a = state.accounts.find(x => String(x.steamId) === String(sid));
      const m = menuItem.dataset.menu;
      hideFloating();
      if (!a) return;
      if (m === 'credentials') openCredentials(a);
      if (m === 'refresh') await run(() => native('refresh_account', sid));
      if (m === 'profile') await native('open_profile', sid);
      if (m === 'copy') await run(() => native('copy_steam_id', sid));
      if (m === 'favorite') await run(() => native('toggle_favorite', sid), false);
      if (m === 'comp') await run(() => native('toggle_comp', sid));
      if (m === 'delete' && confirm(`Remove ${a.personaName} from SAM?`)) await run(() => native('delete_account', sid));
      return;
    }

    if (e.target.closest('#save-credentials')) {
      const sid = e.target.closest('#save-credentials').dataset.steamId;
      const r = await run(() => native('save_credentials', sid, $('#credential-user').value, $('#credential-pass').value, $('#credential-store').checked));
      if (r?.ok) closeModal();
      return;
    }
    if (e.target.closest('#forget-password')) {
      const sid = e.target.closest('#forget-password').dataset.steamId;
      const r = await run(() => native('forget_password', sid));
      if (r?.ok) closeModal();
      return;
    }

    if (e.target.closest('#save-api-key')) {
      const r = await run(() => native('save_api_key', $('#api-key-input').value));
      if (r?.ok) openSettings();
      return;
    }
    if (e.target.closest('#clear-api-key')) {
      const r = await run(() => native('clear_api_key'));
      if (r?.ok) openSettings();
      return;
    }
    if (e.target.closest('#open-api-page')) { await native('open_api_key_page'); return; }

    if (e.target.closest('#choose-bulk-file')) {
      setBusy(true);
      try {
        const r = await native('choose_bulk_login_file');
        if (r?.bulk) bulk = r.bulk;
        if (r?.message && !r?.cancelled) toast(r.message, r.ok === false ? 'error' : 'success');
        renderBulkModal();
      } catch (err) { toast(err.message, 'error'); } finally { setBusy(false); }
      return;
    }
    if (e.target.closest('#start-bulk')) {
      const r = await run(() => native('start_bulk_login', true));
      if (r?.bulk) bulk = r.bulk;
      state.bulkLoginActive = !!bulk?.active;
      render();
      renderBulkModal();
      return;
    }
    if (e.target.closest('#cancel-bulk')) {
      const r = await run(() => native('cancel_bulk_login'));
      if (r?.bulk) bulk = r.bulk;
      renderBulkModal();
      return;
    }

    if (!e.target.closest('#popover,#context-menu')) hideFloating();
  });

  $('#search-input').addEventListener('input', e => { ui.query = e.target.value; render(); });
  $('#sort-select').addEventListener('change', e => { ui.sort = e.target.value; localStorage.setItem('sam.sort', ui.sort); render(); });
  $('#modal-layer').addEventListener('click', e => { if (e.target.matches('.modal-backdrop')) closeModal(); });

  $$('[data-window-action]').forEach(b => b.addEventListener('click', () => native('window_action', b.dataset.windowAction)));

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { hideFloating(); closeModal(); }
    if (e.ctrlKey && e.key.toLowerCase() === 'f') { e.preventDefault(); $('#search-input').focus(); }
    if (e.ctrlKey && e.key.toLowerCase() === 'r') { e.preventDefault(); run(() => native('refresh_all')); }
    if (e.ctrlKey && e.key.toLowerCase() === 'n') { e.preventDefault(); run(() => native('add_account')); }
  });

  window.Native = {
    onEvent(event, payload) {
      if (event === 'state') applyState(payload);
      if (event === 'toast') toast(payload?.message, payload?.kind || 'info');
      if (event === 'bulk-status') {
        bulk = payload;
        state.bulkLoginActive = !!payload?.active;
        render();
        renderBulkModal();
      }
      if (event === 'window-state') document.body.classList.toggle('maximized', !!payload?.maximized);
    }
  };

  async function load() {
    try {
      const next = await native('get_state');
      applyState(next);
      native('startup_refresh').catch(() => {});
      try {
        bulk = await native('get_bulk_login_status');
        state.bulkLoginActive = !!bulk?.active;
        render();
      } catch {}
    } catch (e) {
      toast(`Startup failed: ${e.message || e}`, 'error');
    }
  }

  window.addEventListener('pywebviewready', load);
  setInterval(() => {
    state.accounts.forEach(a => {
      if (a.vcbndUntil && Number(a.vcbndUntil) <= Date.now() / 1000) a.vcbndUntil = 0;
    });
    render();
  }, 30000);
})();
