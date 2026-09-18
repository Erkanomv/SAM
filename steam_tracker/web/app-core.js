  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const storageGet = (key, fallback = '') => { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } };
  const storageSet = (key, value) => { try { localStorage.setItem(key, value); } catch {} };

  const state = {
    accounts: [],
    apiKeyConfigured: false,
    dataModeText: 'Public Steam data',
    steamInstalled: true,
    bulkLoginActive: false,
    version: '0.5.0',
  };

  const ui = {
    status: storageGet('steamTracker.status', 'ALL'),
    sort: storageGet('steamTracker.sort', 'Favorite'),
    query: '',
    busy: false,
  };

  const bulkUi = { status: null };
  let modalView = '';

  const icons = {
    heart: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.8 4.6a5.4 5.4 0 00-7.6 0L12 5.8l-1.2-1.2a5.4 5.4 0 00-7.6 7.6l1.2 1.2L12 21l7.6-7.6 1.2-1.2a5.4 5.4 0 000-7.6z"/></svg>`,
    more: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/></svg>`,
    clock: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.8 1.8"/></svg>`,
    chevron: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>`,
    user: `<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.2"/><path d="M5 20a7 7 0 0114 0"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 10-2.34 5.66M20 4v7h-7"/></svg>`,
    external: `<svg viewBox="0 0 24 24"><path d="M14 5h5v5M13 11l6-6M19 13v6H5V5h6"/></svg>`,
    copy: `<svg viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 00-2-2H5a2 2 0 00-2 2v9a2 2 0 002 2h3"/></svg>`,
    pin: `<svg viewBox="0 0 24 24"><path d="M9 4h6l-1 5 3 3H7l3-3-1-5zM12 12v8"/></svg>`,
    trash: `<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13"/></svg>`,
    close: `<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
    key: `<svg viewBox="0 0 24 24"><circle cx="8" cy="15" r="4"/><path d="M11 12l8-8m-3 3l2 2m-5 1l2 2"/></svg>`,
    shield: `<svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.6-2.8 8-7 10-4.2-2-7-5.4-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/></svg>`,
    upload: `<svg viewBox="0 0 24 24"><path d="M12 4v10M8 8l4-4 4 4"/><path d="M5 13v5a2 2 0 002 2h10a2 2 0 002-2v-5"/></svg>`,
    file: `<svg viewBox="0 0 24 24"><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v5h5"/></svg>`,
    check: `<svg viewBox="0 0 24 24"><path d="M5 12l4 4 10-10"/></svg>`,
    stop: `<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>`,
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  function safeUrl(value) {
    const url = String(value || '');
    return /^https:\/\//i.test(url) ? url.replace(/"/g, '%22') : '';
  }

  function formatHours(hours) {
    const n = Number(hours || 0);
    if (!n) return '—';
    if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k h`;
    if (n >= 100) return `${Math.round(n).toLocaleString()} h`;
    return `${n.toFixed(1)} h`;
  }

  function remainingText(until) {
    let sec = Math.max(0, Math.floor(Number(until || 0) - Date.now() / 1000));
    if (!sec) return '';
    const days = Math.floor(sec / 86400); sec %= 86400;
    const hours = Math.floor(sec / 3600); sec %= 3600;
    const minutes = Math.floor(sec / 60);
    if (days) return `${days}d ${hours}h ${minutes}m`;
    if (hours) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  }

  function isVcbnd(account) {
    return Number(account.vcbndUntil || 0) > Date.now() / 1000;
  }

  function accountStatus(account) {
    if (Boolean(account.comp)) return 'COMP';
    return isVcbnd(account) ? 'VCBND' : 'UNBND';
  }

  function cardHtml(account) {
    const active = isVcbnd(account);
    const status = accountStatus(account);
    const comp = status === 'COMP';
    const topGames = Array.isArray(account.topGames) ? account.topGames : [];
    const top = topGames[0] || {};
    const hero = safeUrl(top.header_url);
    const heroThumb = safeUrl(top.header_url || top.icon_url);
    const avatar = safeUrl(account.avatarUrl);
    const mini = topGames.slice(0, 5).map(g => safeUrl(g.icon_url)).filter(Boolean)
      .map(src => `<img class="mini-icon" src="${src}" loading="lazy" decoding="async" alt="">`).join('');
    const strip = topGames.slice(0, 7).map(g => safeUrl(g.header_url || g.icon_url)).filter(Boolean)
      .map(src => `<img class="game-thumb" src="${src}" loading="lazy" decoding="async" alt="">`).join('');
    const name = escapeHtml(account.personaName || account.steamId);
    const gameName = escapeHtml(account.topGameName || 'STEAM');
    const gameShort = escapeHtml((account.topGameName || 'TOP GAME').toUpperCase().slice(0, 18));
    const loginReady = account.loginUsername && account.hasPassword;

    return `<article class="account-card" data-steam-id="${escapeHtml(account.steamId)}">
      <div class="card-hero">
        ${hero ? `<img class="card-hero-art" src="${hero}" loading="lazy" decoding="async" alt="">` : ''}
        <div class="card-hero-content">
          <div class="game-badge">${heroThumb ? `<img src="${heroThumb}" loading="lazy" decoding="async" alt="">` : ''}</div>
          <div class="hero-copy">
            <div class="hero-title">${gameName}</div>
            <div class="hero-meta">${formatHours(account.topGameHours)} · MOST PLAYED</div>
          </div>
          <button class="favorite-btn ${account.favorite ? 'active' : ''}" data-action="favorite" aria-label="${account.favorite ? 'Unpin' : 'Pin'} account">${icons.heart}</button>
        </div>
      </div>
      <div class="card-body">
        <div class="profile-row">
          <div class="avatar-wrap">${avatar ? `<img src="${avatar}" loading="lazy" decoding="async" alt="">` : ''}</div>
          <div class="account-copy">
            <div class="account-name">${name}</div>
            <div class="account-subline"><span class="presence-dot ${Number(account.personaState) > 0 ? 'online' : ''}"></span>${Number(account.personaState) > 0 ? 'Online' : 'Offline'}</div>
            <div class="mini-icons">${mini}</div>
          </div>
          <div class="account-level">${Number(account.steamLevel) >= 0 ? `LVL ${Number(account.steamLevel)}` : 'LVL —'}</div>
        </div>

        <div class="stats-row">
          <div class="stat-box"><span class="stat-label">HOURS · ${gameShort}</span><strong class="stat-value">${formatHours(account.topGameHours)}</strong></div>
          <div class="stat-box"><span class="stat-label">TOTAL PLAYTIME</span><strong class="stat-value">${formatHours(account.totalHours)}</strong></div>
        </div>

        <div class="status-row" data-timer-until="${Number(account.vcbndUntil || 0)}" data-comp="${comp ? '1' : '0'}">
          <span class="status-label">${comp ? 'ACCOUNT STATUS' : (active ? 'VCBND TIMER' : 'ACCOUNT STATUS')}</span>
          <span class="status-remaining">${!comp && active ? remainingText(account.vcbndUntil) : ''}</span>
          <strong class="status-value ${status.toLowerCase()}">${status}</strong>
        </div>

        <div class="library-block">
          <div class="library-head">LIBRARY <span class="library-count">${Number(account.gameCount || 0).toLocaleString()}</span>${icons.chevron}</div>
          <div class="game-strip">${strip}</div>
        </div>

        <div class="card-actions">
          <button class="card-menu-btn" data-action="menu" aria-label="Account actions">${icons.more}</button>
          <button class="timer-btn ${active ? 'active' : ''}" data-action="timer">${icons.clock}<span>${active ? remainingText(account.vcbndUntil) : 'Set timer'}</span></button>
          <button class="comp-btn ${account.comp ? 'active' : ''}" data-action="comp" aria-pressed="${account.comp ? 'true' : 'false'}">COMP</button>
          <button class="login-btn" data-action="login">${loginReady ? 'LOGIN' : 'SET LOGIN'}</button>
        </div>
      </div>
    </article>`;
  }

  function filteredAccounts() {
    const q = ui.query.trim().toLowerCase();
    let items = state.accounts.filter(a => {
      const status = accountStatus(a);
      if (ui.status !== 'ALL' && ui.status !== status) return false;
      if (q) {
        const hay = `${a.personaName || ''} ${a.steamId || ''} ${a.loginUsername || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    items = [...items].sort((a, b) => {
      if (ui.sort === 'Playtime') return Number(b.totalHours || 0) - Number(a.totalHours || 0);
      if (ui.sort === 'Timer') {
        const av = isVcbnd(a) ? Number(a.vcbndUntil) : Number.MAX_SAFE_INTEGER;
        const bv = isVcbnd(b) ? Number(b.vcbndUntil) : Number.MAX_SAFE_INTEGER;
        return av - bv;
      }
      if (ui.sort === 'Name') return String(a.personaName || '').localeCompare(String(b.personaName || ''), undefined, { sensitivity: 'base' });
      if (ui.sort === 'Date added') return Number(b.dateAdded || 0) - Number(a.dateAdded || 0);
      if (Boolean(a.favorite) !== Boolean(b.favorite)) return a.favorite ? -1 : 1;
      return String(a.personaName || '').localeCompare(String(b.personaName || ''), undefined, { sensitivity: 'base' });
    });
    return items;
  }

  function render() {
    const all = state.accounts.length;
    const vcbnd = state.accounts.filter(a => accountStatus(a) === 'VCBND').length;
    const unbnd = state.accounts.filter(a => accountStatus(a) === 'UNBND').length;
    const comp = state.accounts.filter(a => accountStatus(a) === 'COMP').length;
    const shown = filteredAccounts();

    $('#all-count').textContent = all;
    $('#unbnd-count').textContent = unbnd;
    $('#vcbnd-count').textContent = vcbnd;
    $('#comp-count').textContent = comp;
    $('#shown-count').textContent = `${shown.length} shown`;
    $('#account-summary').textContent = all ? `${all} linked account${all === 1 ? '' : 's'}` : 'No accounts linked';
    $('#connection-text').textContent = state.dataModeText || 'Public Steam data';
    $('#connection-pill').classList.toggle('public', !state.apiKeyConfigured);
    $('#bulk-login-btn')?.classList.toggle('queue-active', Boolean(state.bulkLoginActive));

    $$('.filter-chip').forEach(b => b.classList.toggle('active', b.dataset.filter === ui.status));
    $('#sort-select').value = ui.sort;

    const grid = $('#account-grid');
    grid.innerHTML = shown.map(cardHtml).join('');

    const empty = $('#empty-state');
    if (!shown.length) {
      empty.classList.remove('hidden');
      if (all && (ui.query || ui.status !== 'ALL')) {
        $('#empty-title').textContent = 'Nothing matches';
        $('#empty-copy').textContent = 'Try a different search or account status filter.';
        $('#empty-add-btn').classList.add('hidden');
      } else {
        $('#empty-title').textContent = 'No accounts yet';
        $('#empty-copy').textContent = 'Link a Steam account to start building your library.';
        $('#empty-add-btn').classList.remove('hidden');
      }
    } else {
      empty.classList.add('hidden');
    }
  }

  function setState(next) {
    if (!next || typeof next !== 'object') return;
    Object.assign(state, next);
    render();
  }

  function findAccount(steamId) {
    return state.accounts.find(a => String(a.steamId) === String(steamId));
  }

  function showToast(message, kind = 'info') {
    if (!message) return;
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.innerHTML = `<span class="toast-indicator"></span><span>${escapeHtml(message)}</span>`;
    $('#toast-stack').appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(6px)';
      setTimeout(() => el.remove(), 180);
    }, 3600);
  }

  function setBusy(value) {
    ui.busy = Boolean(value);
    document.body.classList.toggle('busy', ui.busy);
  }

  async function api(method, ...args) {
    if (!window.pywebview?.api?.[method]) throw new Error(`Native bridge is unavailable: ${method}`);
    return await window.pywebview.api[method](...args);
  }

  async function runBusy(fn, { toast = true } = {}) {
    if (ui.busy) return null;
    setBusy(true);
    try {
      const result = await fn();
      if (result?.state) setState(result.state);
      if (toast && result?.message) showToast(result.message, result.ok === false ? 'error' : 'success');
      return result;
    } catch (err) {
      showToast(err?.message || String(err), 'error');
      return null;
    } finally {
      setBusy(false);
    }
  }
