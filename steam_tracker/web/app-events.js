  // UI events
  $('#search-input').addEventListener('input', e => { ui.query = e.target.value; render(); });
  $('#sort-select').addEventListener('change', e => { ui.sort = e.target.value; storageSet('steamTracker.sort', ui.sort); render(); });
  $('#status-filters').addEventListener('click', e => {
    const btn = e.target.closest('[data-filter]');
    if (!btn) return;
    ui.status = btn.dataset.filter;
    storageSet('steamTracker.status', ui.status);
    render();
  });

  $('#account-grid').addEventListener('click', async e => {
    const card = e.target.closest('.account-card');
    const action = e.target.closest('[data-action]')?.dataset.action;
    if (!card || !action) return;
    const account = findAccount(card.dataset.steamId);
    if (!account) return;
    const trigger = e.target.closest('[data-action]');

    if (action === 'favorite') {
      const result = await runBusy(() => api('toggle_favorite', account.steamId), { toast: false });
      if (result?.state) setState(result.state);
    } else if (action === 'comp') {
      const result = await runBusy(() => api('toggle_comp', account.steamId), { toast: false });
      if (result?.state) setState(result.state);
    } else if (action === 'timer') {
      showTimerPopover(account, trigger);
    } else if (action === 'menu') {
      showMenu(account, trigger);
    } else if (action === 'login') {
      if (!(account.loginUsername && account.hasPassword)) {
        openCredentials(account);
        return;
      }
      const result = await runBusy(() => api('login_account', account.steamId));
      if (result?.needsCredentials) openCredentials(findAccount(account.steamId) || account);
    }
  });

  $('#account-grid').addEventListener('contextmenu', e => {
    const card = e.target.closest('.account-card');
    if (!card) return;
    e.preventDefault();
    const account = findAccount(card.dataset.steamId);
    if (!account) return;
    showMenu(account, card);
    const menu = $('#context-menu');
    menu.style.left = `${Math.min(e.clientX, window.innerWidth - 206)}px`;
    menu.style.top = `${Math.min(e.clientY, window.innerHeight - menu.offsetHeight - 10)}px`;
  });

  $('#context-menu').addEventListener('click', async e => {
    const item = e.target.closest('[data-menu]');
    if (!item) return;
    const account = findAccount($('#context-menu').dataset.steamId);
    hideMenu();
    if (!account) return;
    const action = item.dataset.menu;
    if (action === 'credentials') openCredentials(account);
    if (action === 'refresh') await runBusy(() => api('refresh_account', account.steamId));
    if (action === 'profile') await api('open_profile', account.steamId);
    if (action === 'copy') { const r = await api('copy_steam_id', account.steamId); showToast(r.message, r.ok ? 'success' : 'error'); }
    if (action === 'favorite') await runBusy(() => api('toggle_favorite', account.steamId), { toast: false });
    if (action === 'comp') await runBusy(() => api('toggle_comp', account.steamId), { toast: false });
    if (action === 'delete') openDelete(account);
  });

  $('#popover').addEventListener('click', async e => {
    if (e.target.id === 'apply-timer') {
      const sid = e.target.dataset.steamId;
      const days = $('#timer-days').value;
      const result = await runBusy(() => api('set_timer', sid, days));
      if (result?.ok) hidePopover();
    }
    if (e.target.id === 'clear-timer') {
      const result = await runBusy(() => api('clear_timer', e.target.dataset.steamId));
      if (result?.ok) hidePopover();
    }
  });
  $('#popover').addEventListener('keydown', e => { if (e.key === 'Enter' && $('#apply-timer')) $('#apply-timer').click(); });

  $('#modal-layer').addEventListener('click', async e => {
    if (e.target.closest('[data-close-modal]')) { closeModal(); return; }
    if (e.target.closest('#choose-bulk-file')) { await chooseBulkFile(); return; }
    if (e.target.closest('#start-bulk-login')) {
      const store = Boolean($('#bulk-store-passwords')?.checked);
      const result = await api('start_bulk_login', store);
      if (result?.bulk) bulkUi.status = result.bulk;
      if (result?.message) showToast(result.message, result.ok ? 'success' : 'error');
      renderBulkModal();
      return;
    }
    if (e.target.closest('#cancel-bulk-login')) {
      const result = await api('cancel_bulk_login');
      if (result?.bulk) bulkUi.status = result.bulk;
      if (result?.message) showToast(result.message, result.ok ? 'info' : 'error');
      renderBulkModal();
      return;
    }
    if (e.target.closest('#clear-bulk-file') || e.target.closest('#bulk-import-another')) {
      const result = await api('clear_bulk_login_selection');
      if (result?.bulk) bulkUi.status = result.bulk;
      renderBulkModal();
      if (e.target.closest('#bulk-import-another')) await chooseBulkFile();
      return;
    }
    if (e.target.id === 'save-api-key') {
      const result = await runBusy(() => api('save_api_key', $('#api-key-input').value));
      if (result?.ok) openSettings();
    }
    if (e.target.id === 'open-api-page') await api('open_api_key_page');
    if (e.target.id === 'clear-api-key') {
      const result = await runBusy(() => api('clear_api_key'));
      if (result?.ok) openSettings();
    }
    if (e.target.id === 'save-credentials') {
      const sid = e.target.dataset.steamId;
      const result = await runBusy(() => api('save_credentials', sid, $('#credential-user').value, $('#credential-pass').value, $('#credential-store').checked));
      if (result?.ok) closeModal();
    }
    if (e.target.id === 'forget-password') {
      const result = await runBusy(() => api('forget_password', e.target.dataset.steamId));
      if (result?.ok) closeModal();
    }
    if (e.target.id === 'confirm-delete') {
      const result = await runBusy(() => api('delete_account', e.target.dataset.steamId));
      if (result?.ok) closeModal();
    }
  });

  document.addEventListener('error', e => {
    if (e.target instanceof HTMLImageElement) e.target.style.display = 'none';
  }, true);

  document.addEventListener('contextmenu', e => {
    if (!e.target.closest('.account-card')) e.preventDefault();
  });

  $('.main-content').addEventListener('scroll', () => { hidePopover(); hideMenu(); }, { passive: true });

  document.addEventListener('pointerdown', e => {
    if (!e.target.closest('#popover') && !e.target.closest('[data-action="timer"]')) hidePopover();
    if (!e.target.closest('#context-menu') && !e.target.closest('[data-action="menu"]')) hideMenu();
  });

  $('#refresh-all-btn').addEventListener('click', () => runBusy(() => api('refresh_all')));
  $('#settings-btn').addEventListener('click', openSettings);
  $('#bulk-login-btn').addEventListener('click', openBulkLogin);
  const addAccount = async () => {
    const result = await api('add_account');
    if (result?.message) showToast(result.message, result.ok ? 'success' : 'error');
  };
  $('#add-account-btn').addEventListener('click', addAccount);
  $('#empty-add-btn').addEventListener('click', addAccount);

  $$('.window-control').forEach(btn => btn.addEventListener('click', () => api('window_action', btn.dataset.windowAction)));
  $$('.pywebview-drag-region').forEach(region => region.addEventListener('dblclick', () => api('window_action', 'maximize')));

  document.addEventListener('keydown', e => {
    const ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && e.key.toLowerCase() === 'f') { e.preventDefault(); $('#search-input').focus(); $('#search-input').select(); }
    if (ctrl && e.key.toLowerCase() === 'r') { e.preventDefault(); $('#refresh-all-btn').click(); }
    if (ctrl && e.key.toLowerCase() === 'n') { e.preventDefault(); addAccount(); }
    if (ctrl && e.key === '1') { e.preventDefault(); ui.status = 'ALL'; render(); }
    if (ctrl && e.key === '2') { e.preventDefault(); ui.status = 'UNBND'; render(); }
    if (ctrl && e.key === '3') { e.preventDefault(); ui.status = 'VCBND'; render(); }
    if (ctrl && e.key === '4') { e.preventDefault(); ui.status = 'COMP'; render(); }
    if (e.key === 'Escape') { hidePopover(); hideMenu(); closeModal(); }
  });

  window.Native = {
    onEvent(event, payload) {
      if (event === 'state') setState(payload);
      if (event === 'toast') showToast(payload?.message, payload?.kind || 'info');
      if (event === 'window-state') document.body.classList.toggle('window-maximized', Boolean(payload?.maximized));
      if (event === 'bulk-status') {
        bulkUi.status = payload || null;
        state.bulkLoginActive = Boolean(payload?.active);
        $('#bulk-login-btn')?.classList.toggle('queue-active', state.bulkLoginActive);
        if (modalView === 'bulk') renderBulkModal();
      }
    }
  };

  const preview = new URLSearchParams(location.search).get('preview') === '1';
  if (preview) {
    const now = Math.floor(Date.now() / 1000);
    setState({
      version: '0.5.0',
      apiKeyConfigured: true,
      dataModeText: 'Web API key configured',
      steamInstalled: true,
      steamPath: 'C:\\Program Files (x86)\\Steam\\steam.exe',
      accounts: [
        {steamId:'76561198000000001',personaName:'Atlas',avatarUrl:'',personaState:0,steamLevel:22,loginUsername:'atlas_demo',hasPassword:true,vcbndUntil:0,favorite:true,topGameName:'RUST',topGameHours:0,totalHours:5442.3,gameCount:59,dateAdded:3,topGames:[]},
        {steamId:'76561198000000002',personaName:'Nova',avatarUrl:'',personaState:1,steamLevel:11,loginUsername:'nova_demo',hasPassword:true,vcbndUntil:now+6*86400,favorite:false,topGameName:'Counter-Strike 2',topGameHours:143,totalHours:2315,gameCount:60,dateAdded:2,topGames:[]},
        {steamId:'76561198000000003',personaName:'Orion',avatarUrl:'',personaState:0,steamLevel:14,loginUsername:'orion_demo',hasPassword:false,vcbndUntil:0,favorite:false,comp:true,topGameName:'RUST',topGameHours:48,totalHours:2131.3,gameCount:62,dateAdded:1,topGames:[]}
      ]
    });
  } else {
    window.addEventListener('pywebviewready', loadInitialState, { once: true });
    if (window.pywebview?.api) loadInitialState();
  }

  setInterval(updateTimerNodes, 10000);
