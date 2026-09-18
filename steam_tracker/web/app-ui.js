  function openModal(html, view = '') {
    hidePopover();
    hideMenu();
    modalView = view;
    const layer = $('#modal-layer');
    $('#modal-sheet').innerHTML = html;
    layer.classList.remove('hidden');
    layer.setAttribute('aria-hidden', 'false');
    setTimeout(() => $('#modal-sheet input:not([type="checkbox"])')?.focus(), 70);
  }

  function closeModal() {
    const layer = $('#modal-layer');
    layer.classList.add('hidden');
    layer.setAttribute('aria-hidden', 'true');
    $('#modal-sheet').innerHTML = '';
    modalView = '';
  }

  function modalHeader(kicker, title) {
    return `<header class="sheet-head"><div class="sheet-head-copy"><div class="sheet-kicker">${escapeHtml(kicker)}</div><h2 class="sheet-title">${escapeHtml(title)}</h2></div><button class="sheet-close" data-close-modal aria-label="Close">${icons.close}</button></header>`;
  }

  function openSettings() {
    openModal(`${modalHeader('STEAM TRACKER', 'Settings')}
      <div class="sheet-body">
        <section class="settings-section">
          <h3 class="section-label">Steam data</h3>
          <p class="section-copy">The API key is optional. Public accounts still work without one; a valid key makes bulk profile refreshes faster and adds Steam levels.</p>
          <div class="status-card">
            <div class="status-card-icon">${icons.shield}</div>
            <div class="status-card-copy"><strong>${state.apiKeyConfigured ? 'Web API key configured' : 'Public data mode'}</strong><span>${state.apiKeyConfigured ? 'Optional API key stored in Windows Credential Manager' : 'No API key required to link accounts'}</span></div>
          </div>
        </section>
        <section class="settings-section">
          <h3 class="section-label">Optional Web API key</h3>
          <p class="section-copy">If you use one, it is validated against Steam before it is saved.</p>
          <div class="form-grid">
            <div class="field"><label for="api-key-input">API key</label><input id="api-key-input" type="password" placeholder="32-character Steam Web API key" autocomplete="off"><div class="field-note">The key is stored by Windows Credential Manager, never in tracker.sqlite3.</div></div>
            <div class="button-row">
              <button class="btn primary" id="save-api-key">Validate & save</button>
              <button class="btn" id="open-api-page">Get API key</button>
              ${state.apiKeyConfigured ? `<button class="btn danger" id="clear-api-key">Remove saved key</button>` : ''}
            </div>
          </div>
        </section>
        <section class="settings-section">
          <h3 class="section-label">Local Steam</h3>
          <p class="section-copy">The tracker closes the current Steam client and launches the selected account. Steam Guard can still be requested by Steam.</p>
          <div class="status-card"><div class="status-card-icon">${icons.user}</div><div class="status-card-copy"><strong>${state.steamInstalled ? 'Steam client detected' : 'Steam client not found'}</strong><span>${state.steamPath ? escapeHtml(state.steamPath) : 'Install or launch Steam once so the tracker can locate it.'}</span></div></div>
        </section>
        <section class="settings-section">
          <h3 class="section-label">Interface</h3>
          <p class="section-copy">The frontend is rendered by Windows WebView2. Account data and Steam actions stay in the local Python backend.</p>
          <div class="status-card"><div class="status-card-icon">ST</div><div class="status-card-copy"><strong>Steam Tracker v${escapeHtml(state.version)}</strong><span>Local-only database · cached libraries · 50+ account layout</span></div></div>
        </section>
      </div>`);
  }

  function bulkResultIcon(status) {
    if (status === 'success') return icons.check;
    if (status === 'failed') return icons.close;
    if (status === 'running') return '<span class="bulk-spinner"></span>';
    if (status === 'cancelled') return icons.stop;
    return '<span class="bulk-pending-dot"></span>';
  }

  function renderBulkModal() {
    if (modalView !== 'bulk') return;
    const bulk = bulkUi.status || { active:false, phase:'idle', total:0, success:0, failed:0, results:[], selection:null };
    const selection = bulk.selection;
    const results = Array.isArray(bulk.results) ? bulk.results : [];
    const completed = Number(bulk.success || 0) + Number(bulk.failed || 0) + results.filter(r => r.status === 'cancelled').length;
    const progressCount = bulk.active ? Math.max(0, Number(bulk.currentIndex || 0)) : Math.min(Number(bulk.total || 0), Number(bulk.success || 0) + Number(bulk.failed || 0));
    const progress = bulk.total ? Math.max(0, Math.min(100, Math.round((progressCount / bulk.total) * 100))) : 0;
    const isReady = !bulk.active && bulk.phase === 'ready' && selection;
    const isFinished = !bulk.active && ['complete','cancelled'].includes(bulk.phase);

    let body = '';
    if (!selection && !bulk.active && !isFinished) {
      body = `<div class="sheet-body">
        <section class="bulk-intro">
          <div class="bulk-hero-icon">${icons.upload}</div>
          <h3>Import account logins</h3>
          <p>Select a plain text file with one <code>User:Password</code> pair per line. Passwords never get sent to the HTML UI and are only saved after Steam confirms that account locally.</p>
        </section>
        <button class="bulk-file-picker" id="choose-bulk-file">
          <span class="bulk-file-picker-icon">${icons.file}</span>
          <span><strong>Choose .txt file</strong><small>UTF-8 or standard Windows text · up to 500 accounts</small></span>
          <span class="bulk-file-arrow">Browse</span>
        </button>
        <div class="bulk-security-note"><strong>Local only.</strong> The source file is read by the Python backend. Passwords are not written to SQLite or shown in previews/logs.</div>
      </div>`;
    } else if (isReady) {
      const issues = (selection.issues || []).map(x => `<li>${escapeHtml(x)}</li>`).join('');
      const rows = results.map((r, i) => `<div class="bulk-account-row"><span class="bulk-order">${String(i + 1).padStart(2,'0')}</span><span class="bulk-user">${escapeHtml(r.username)}</span><span class="bulk-row-state pending">READY</span></div>`).join('');
      body = `<div class="sheet-body">
        <div class="bulk-file-card"><span class="bulk-file-card-icon">${icons.file}</span><div><strong>${escapeHtml(selection.filename || 'accounts.txt')}</strong><span>${Number(selection.count || 0)} valid account${Number(selection.count || 0) === 1 ? '' : 's'} loaded</span></div><button class="btn" id="choose-bulk-file">Change</button></div>
        ${issues ? `<div class="bulk-warning"><strong>Skipped lines</strong><ul>${issues}</ul></div>` : ''}
        <div class="bulk-list-head"><span>Login queue</span><span>${Number(selection.count || 0)} accounts</span></div>
        <div class="bulk-account-list">${rows}</div>
        <label class="bulk-store-option"><input type="checkbox" id="bulk-store-passwords" checked><span><strong>Save successful logins</strong><small>Store each password in Windows Credential Manager for one-click login later.</small></span></label>
        <div class="bulk-sequence-note">Steam will close and reopen for each line. Accounts that do not confirm within 55 seconds are marked failed and the queue continues.</div>
        <div class="bulk-footer-actions"><button class="btn" id="clear-bulk-file">Clear</button><button class="btn primary bulk-start" id="start-bulk-login">${icons.upload}<span>Start ${Number(selection.count || 0)} logins</span></button></div>
      </div>`;
    } else {
      const phaseText = bulk.phase === 'switching' ? 'Restarting Steam' : bulk.phase === 'waiting' ? 'Waiting for sign-in' : bulk.phase === 'added' ? 'Account added' : bulk.phase === 'cancelling' ? 'Stopping queue' : bulk.phase === 'cancelled' ? 'Queue stopped' : bulk.phase === 'complete' ? 'Queue complete' : 'Preparing queue';
      const rows = results.map((r, i) => `<div class="bulk-account-row ${escapeHtml(r.status || 'pending')}">
        <span class="bulk-result-icon ${escapeHtml(r.status || 'pending')}">${bulkResultIcon(r.status)}</span>
        <span class="bulk-user"><strong>${escapeHtml(r.username)}</strong>${r.message ? `<small>${escapeHtml(r.message)}</small>` : ''}</span>
        <span class="bulk-row-state ${escapeHtml(r.status || 'pending')}">${r.status === 'success' ? 'ADDED' : r.status === 'failed' ? 'FAILED' : r.status === 'running' ? 'NOW' : r.status === 'cancelled' ? 'SKIPPED' : 'WAITING'}</span>
      </div>`).join('');
      body = `<div class="sheet-body">
        <div class="bulk-progress-head"><div><span class="bulk-progress-kicker">${escapeHtml(phaseText)}</span><strong>${bulk.active && bulk.currentUsername ? escapeHtml(bulk.currentUsername) : isFinished ? `${Number(bulk.success || 0)} added · ${Number(bulk.failed || 0)} failed` : 'Starting…'}</strong></div><span>${bulk.active ? `${Math.min(Number(bulk.currentIndex || 0) + 1, Number(bulk.total || 0))}/${Number(bulk.total || 0)}` : `${Number(bulk.total || 0)}/${Number(bulk.total || 0)}`}</span></div>
        <div class="bulk-progress-track"><div class="bulk-progress-fill" style="width:${isFinished ? 100 : progress}%"></div></div>
        <div class="bulk-metrics"><div><span>Added</span><strong>${Number(bulk.success || 0)}</strong></div><div><span>Failed</span><strong>${Number(bulk.failed || 0)}</strong></div><div><span>Remaining</span><strong>${Math.max(0, Number(bulk.total || 0) - completed)}</strong></div></div>
        <div class="bulk-list-head"><span>Account activity</span><span>${escapeHtml(phaseText)}</span></div>
        <div class="bulk-account-list running">${rows}</div>
        ${bulk.active ? `<div class="bulk-footer-actions"><span class="bulk-running-note">Keep this app open while Steam cycles through the queue.</span><button class="btn danger" id="cancel-bulk-login">${icons.stop}<span>Stop queue</span></button></div>` : `<div class="bulk-footer-actions"><button class="btn" data-close-modal>Close</button><button class="btn primary" id="bulk-import-another">Import another file</button></div>`}
      </div>`;
    }

    $('#modal-sheet').innerHTML = `${modalHeader('LOCAL STEAM', 'Bulk login')}${body}`;
  }

  async function openBulkLogin() {
    openModal(`${modalHeader('LOCAL STEAM', 'Bulk login')}<div class="sheet-body"><div class="bulk-loading"><span class="bulk-spinner"></span><span>Loading queue…</span></div></div>`, 'bulk');
    try {
      bulkUi.status = await api('get_bulk_login_status');
      renderBulkModal();
    } catch (err) {
      showToast(err?.message || String(err), 'error');
      closeModal();
    }
  }

  async function chooseBulkFile() {
    setBusy(true);
    try {
      const result = await api('choose_bulk_login_file');
      if (result?.bulk) bulkUi.status = result.bulk;
      if (result?.ok) showToast(result.message, 'success');
      else if (!result?.cancelled && result?.message) showToast(result.message, 'error');
      renderBulkModal();
    } catch (err) {
      showToast(err?.message || String(err), 'error');
    } finally {
      setBusy(false);
    }
  }

  function openCredentials(account) {
    if (!account) return;
    openModal(`${modalHeader('LOCAL STEAM LOGIN', 'Login credentials')}
      <div class="sheet-body">
        <div class="credential-avatar-row">
          ${safeUrl(account.avatarUrl) ? `<img src="${safeUrl(account.avatarUrl)}" alt="">` : '<div class="avatar-wrap"></div>'}
          <div><strong>${escapeHtml(account.personaName)}</strong><span>SteamID ${escapeHtml(account.steamId)}</span></div>
        </div>
        <div class="form-grid">
          <div class="field"><label for="credential-user">Steam account name</label><input id="credential-user" type="text" value="${escapeHtml(account.loginUsername || '')}" autocomplete="username"><div class="field-note">Use the actual Steam login/account name, not the public display name.</div></div>
          <div class="field"><label for="credential-pass">Password</label><input id="credential-pass" type="password" placeholder="${account.hasPassword ? 'Stored password — type to replace it' : 'Enter password'}" autocomplete="current-password"></div>
          <label class="check-row"><input id="credential-store" type="checkbox" ${account.hasPassword ? 'checked' : ''}> Store password in Windows Credential Manager</label>
          <div class="button-row">
            <button class="btn primary" id="save-credentials" data-steam-id="${escapeHtml(account.steamId)}">Save login</button>
            ${account.hasPassword ? `<button class="btn danger" id="forget-password" data-steam-id="${escapeHtml(account.steamId)}">Forget stored password</button>` : ''}
          </div>
        </div>
      </div>`);
  }

  function openDelete(account) {
    openModal(`${modalHeader('REMOVE ACCOUNT', 'Remove from tracker?')}
      <div class="sheet-body">
        <section class="settings-section">
          <h3 class="section-label">${escapeHtml(account.personaName)}</h3>
          <p class="section-copy">This removes the account, cached game data, timer, and its saved local password from this tracker. It does not modify the Steam account.</p>
          <div class="button-row"><button class="btn" data-close-modal>Cancel</button><button class="btn danger" id="confirm-delete" data-steam-id="${escapeHtml(account.steamId)}">Remove account</button></div>
        </section>
      </div>`);
  }

  function positionFloating(el, anchor, preferredWidth = 250) {
    const r = anchor.getBoundingClientRect();
    const margin = 10;
    const width = preferredWidth;
    const left = Math.min(window.innerWidth - width - margin, Math.max(margin, r.right - width));
    const estimatedHeight = el.offsetHeight || 180;
    let top = r.bottom + 7;
    if (top + estimatedHeight > window.innerHeight - margin) top = Math.max(margin, r.top - estimatedHeight - 7);
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
  }

  function showTimerPopover(account, anchor) {
    hideMenu();
    const pop = $('#popover');
    const active = isVcbnd(account);
    pop.innerHTML = `<h3 class="popover-title">${active ? 'Update VCBND timer' : 'Set VCBND timer'}</h3>
      <p class="popover-copy">Enter any number of days. The timer persists while the app is closed.</p>
      <div class="timer-entry"><input id="timer-days" inputmode="decimal" placeholder="Days, e.g. 7"><button id="apply-timer" data-steam-id="${escapeHtml(account.steamId)}">Set</button></div>
      ${active ? `<div class="popover-actions"><button class="popover-clear" id="clear-timer" data-steam-id="${escapeHtml(account.steamId)}">Clear timer</button></div>` : ''}`;
    pop.classList.remove('hidden');
    requestAnimationFrame(() => {
      positionFloating(pop, anchor, 250);
      $('#timer-days')?.focus();
    });
  }

  function hidePopover() { $('#popover').classList.add('hidden'); }

  function showMenu(account, anchor) {
    hidePopover();
    const menu = $('#context-menu');
    menu.innerHTML = `
      <button class="menu-item" data-menu="credentials">${icons.user}<span>Edit login</span></button>
      <button class="menu-item" data-menu="refresh">${icons.refresh}<span>Refresh account</span></button>
      <button class="menu-item" data-menu="profile">${icons.external}<span>Open Steam profile</span></button>
      <button class="menu-item" data-menu="copy">${icons.copy}<span>Copy SteamID</span></button>
      <button class="menu-item" data-menu="favorite">${icons.pin}<span>${account.favorite ? 'Unpin account' : 'Pin account'}</span></button>
      <button class="menu-item" data-menu="comp">${icons.shield}<span>${account.comp ? 'Clear COMP' : 'Mark as COMP'}</span></button>
      <div class="menu-separator"></div>
      <button class="menu-item danger" data-menu="delete">${icons.trash}<span>Remove account</span></button>`;
    menu.dataset.steamId = account.steamId;
    menu.classList.remove('hidden');
    requestAnimationFrame(() => positionFloating(menu, anchor, 196));
  }

  function hideMenu() { $('#context-menu').classList.add('hidden'); }

  let initialLoaded = false;
  async function loadInitialState() {
    if (initialLoaded) return;
    initialLoaded = true;
    try {
      const next = await api('get_state');
      setState(next);
      api('startup_refresh').catch(() => {});
    } catch (err) {
      showToast(`Could not start native backend: ${err?.message || err}`, 'error');
    }
  }

  function updateTimerNodes() {
    let expired = false;
    $$('[data-timer-until]').forEach(row => {
      const until = Number(row.dataset.timerUntil || 0);
      const active = until > Date.now() / 1000;
      const card = row.closest('.account-card');
      const value = $('.status-value', row);
      const remaining = $('.status-remaining', row);
      const label = $('.status-label', row);
      const timerBtn = $('.timer-btn', card);
      const comp = row.dataset.comp === '1';
      if (active) {
        if (!comp) {
          label.textContent = 'VCBND TIMER';
          remaining.textContent = remainingText(until);
          value.textContent = 'VCBND';
          value.className = 'status-value vcbnd';
        }
        timerBtn?.classList.add('active');
        $('span', timerBtn).textContent = remainingText(until);
      } else {
        if (until) expired = true;
        row.dataset.timerUntil = '0';
        label.textContent = 'ACCOUNT STATUS';
        remaining.textContent = '';
        value.textContent = comp ? 'COMP' : 'UNBND';
        value.className = `status-value ${comp ? 'comp' : 'unbnd'}`;
        timerBtn?.classList.remove('active');
        $('span', timerBtn).textContent = 'Set timer';
      }
    });
    if (expired) {
      state.accounts.forEach(a => { if (Number(a.vcbndUntil || 0) <= Date.now() / 1000) a.vcbndUntil = 0; });
      render();
    }
  }
