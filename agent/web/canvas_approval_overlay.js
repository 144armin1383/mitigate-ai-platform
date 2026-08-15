(() => {
  'use strict';

  if (window.__MITIGATE_APPROVAL_OVERLAY__) return;
  window.__MITIGATE_APPROVAL_OVERLAY__ = true;

  const API_BASE = '/mitigate-runtime/api';
  const POLL_MS = 5000;
  const READ_TIMEOUT_MS = 8000;
  const ACTION_TIMEOUT_MS = 60000;
  const confirmations = new Map();
  let lastItems = [];
  let actionInProgress = false;
  let loadInProgress = false;

  const css = `
    #mitigate-approval-launcher{position:fixed;left:16px;bottom:118px;z-index:2147483600;border:1px solid rgba(255,255,255,.14);background:#151922;color:#f4f7ff;border-radius:12px;padding:10px 12px;font:600 13px/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.35);cursor:pointer;display:flex;align-items:center;gap:8px}
    #mitigate-approval-launcher:hover{background:#1c2230}
    #mitigate-approval-count{min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:#f2b84b;color:#171106;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800}
    #mitigate-approval-drawer{position:fixed;left:16px;bottom:164px;z-index:2147483601;width:min(420px,calc(100vw - 32px));max-height:min(620px,calc(100vh - 196px));overflow:auto;background:#0f1420;color:#edf2ff;border:1px solid rgba(255,255,255,.14);border-radius:14px;box-shadow:0 16px 50px rgba(0,0,0,.5);font:13px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:none}
    #mitigate-approval-drawer.open{display:block}
    .mitigate-approval-head{position:sticky;top:0;background:#0f1420;border-bottom:1px solid rgba(255,255,255,.1);padding:14px 14px 12px;display:flex;justify-content:space-between;gap:12px;align-items:center}
    .mitigate-approval-title{font-weight:800;font-size:14px}.mitigate-approval-sub{font-size:11px;color:#9aa7be;margin-top:3px}.mitigate-approval-actions{display:flex;gap:6px}.mitigate-mini-btn{border:1px solid rgba(255,255,255,.14);background:#1a2231;color:#e9efff;border-radius:8px;padding:7px 9px;font-weight:700;cursor:pointer}.mitigate-mini-btn:hover{background:#232d3f}.mitigate-approval-body{padding:12px}.mitigate-empty{padding:20px 8px;color:#9aa7be;text-align:center}.mitigate-approval-card{border:1px solid rgba(255,255,255,.11);background:#141b28;border-radius:11px;padding:12px;margin-bottom:10px}.mitigate-approval-card:last-child{margin-bottom:0}.mitigate-row{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.mitigate-id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#b9c7df;overflow-wrap:anywhere}.mitigate-badge{display:inline-flex;border-radius:999px;padding:3px 7px;background:rgba(242,184,75,.15);color:#ffd378;font-size:10px;font-weight:800;white-space:nowrap}.mitigate-reason{color:#a9b5ca;font-size:11px;margin:8px 0}.mitigate-decision-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mitigate-approve-btn,.mitigate-reject-btn{width:100%;border:0;border-radius:9px;font-weight:850;padding:9px 10px;cursor:pointer}.mitigate-approve-btn{background:#3bd09d;color:#07140f}.mitigate-reject-btn{background:#e5484d;color:#fff}.mitigate-approve-btn.confirming{background:#f2b84b;color:#171106}.mitigate-reject-btn.confirming{background:#ff7a80;color:#210507}.mitigate-approve-btn:hover,.mitigate-reject-btn:hover{filter:brightness(1.05)}.mitigate-approve-btn:disabled,.mitigate-reject-btn:disabled{opacity:.55;cursor:wait}.mitigate-error{color:#ff9ba6;font-size:11px;margin-top:8px}.mitigate-success{color:#6ee7b7;font-size:11px;margin-top:8px}
  `;

  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  const launcher = document.createElement('button');
  launcher.id = 'mitigate-approval-launcher';
  launcher.type = 'button';
  launcher.innerHTML = '<span>MITIGATE Approvals</span><span id="mitigate-approval-count">0</span>';

  const drawer = document.createElement('section');
  drawer.id = 'mitigate-approval-drawer';
  drawer.setAttribute('aria-label', 'MITIGATE approval queue');
  drawer.innerHTML = `
    <div class="mitigate-approval-head">
      <div><div class="mitigate-approval-title">Approvals</div><div class="mitigate-approval-sub">Governed manual review inside Canvas</div></div>
      <div class="mitigate-approval-actions"><button class="mitigate-mini-btn" id="mitigate-approval-refresh" type="button">Refresh</button><button class="mitigate-mini-btn" id="mitigate-approval-close" type="button">Close</button></div>
    </div>
    <div class="mitigate-approval-body" id="mitigate-approval-body"><div class="mitigate-empty">Loading…</div></div>`;

  document.body.appendChild(launcher);
  document.body.appendChild(drawer);

  const countEl = document.getElementById('mitigate-approval-count');
  const bodyEl = document.getElementById('mitigate-approval-body');
  const refreshEl = document.getElementById('mitigate-approval-refresh');
  const closeEl = document.getElementById('mitigate-approval-close');

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const decisionKey = (missionId, decision) => `${missionId}:${decision}`;
  const isArmed = (missionId, decision) => {
    const expires = confirmations.get(decisionKey(missionId, decision)) || 0;
    if (expires <= Date.now()) {
      confirmations.delete(decisionKey(missionId, decision));
      return false;
    }
    return true;
  };

  async function api(path, options = {}, timeoutMs = READ_TIMEOUT_MS) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(API_BASE + path, {
        ...options,
        signal: controller.signal,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {'Content-Type': 'application/json', ...(options.headers || {})}
      });
      const text = await response.text();
      let payload = {};
      try { payload = JSON.parse(text); } catch (_) {}
      if (!response.ok) {
        const message = payload?.error?.message || payload?.error?.code || payload?.error || text || `HTTP ${response.status}`;
        throw new Error(`${message} (HTTP ${response.status})`);
      }
      return payload;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('Approval API timed out before the server confirmed a result.');
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function approvalItems(payload) {
    const data = payload?.data || payload || {};
    const items = Array.isArray(data.items) ? data.items : [];
    return items.flatMap(item => {
      if (item?.status !== 'awaiting_approval' || !item?.mission_id) return [];
      return [{
        requestId: item.request_id || '',
        missionId: item.mission_id,
        reason: item.reason || 'manual_review_required'
      }];
    });
  }

  function render(items, transientError = '') {
    lastItems = items;
    countEl.textContent = String(items.length);
    countEl.style.background = items.length ? '#f2b84b' : '#344157';
    countEl.style.color = items.length ? '#171106' : '#d7dfef';
    const errorHtml = transientError ? `<div class="mitigate-error" style="margin:0 0 10px">${esc(transientError)}</div>` : '';
    if (!items.length) {
      bodyEl.innerHTML = errorHtml + '<div class="mitigate-empty">No missions are waiting for approval.</div>';
      return;
    }
    bodyEl.innerHTML = errorHtml + items.map(item => {
      return `
      <article class="mitigate-approval-card" data-mission="${esc(item.missionId)}">
        <div class="mitigate-row"><div><div class="mitigate-id">${esc(item.requestId)}</div><div class="mitigate-id" style="margin-top:4px">${esc(item.missionId)}</div></div><span class="mitigate-badge">Awaiting Approval</span></div>
        <div class="mitigate-reason">${esc(item.reason)}</div>
        <div class="mitigate-decision-row">
          <button class="mitigate-approve-btn" type="button" data-approve="${esc(item.missionId)}">Approve &amp; Merge</button>
          <button class="mitigate-reject-btn" type="button" data-reject="${esc(item.missionId)}">Reject</button>
        </div>
        <div class="mitigate-result" aria-live="polite"></div>
      </article>`;
    }).join('');
    bodyEl.querySelectorAll('[data-approve]').forEach(button => button.addEventListener('click', () => decide(button, 'approve')));
    bodyEl.querySelectorAll('[data-reject]').forEach(button => button.addEventListener('click', () => decide(button, 'reject')));
  }

  async function load() {
    if (actionInProgress || loadInProgress) return lastItems;
    loadInProgress = true;
    try {
      const payload = await api('/approvals');
      const items = approvalItems(payload);
      render(items);
      return items;
    } catch (error) {
      render(lastItems, `Approval API unavailable: ${error.message}`);
      return lastItems;
    } finally {
      loadInProgress = false;
    }
  }

  async function decide(button, decision) {
    const missionId = button.getAttribute(decision === 'approve' ? 'data-approve' : 'data-reject');
    if (!missionId || actionInProgress) return;

    const confirmed = window.confirm(
      decision === 'approve'
        ? `Approve and merge mission ${missionId}?`
        : `Reject mission ${missionId}?`
    );

    if (!confirmed) return;
    const card = button.closest('.mitigate-approval-card');
    const resultEl = card?.querySelector('.mitigate-result');
    const buttons = card ? Array.from(card.querySelectorAll('button')) : [button];
    actionInProgress = true;
    buttons.forEach(item => { item.disabled = true; });
    button.textContent = decision === 'approve' ? 'Approving…' : 'Rejecting…';
    if (resultEl) resultEl.textContent = '';
    window.__MITIGATE_APPROVAL_LAST_RESULT__ = {missionId, decision, state: 'sending', at: new Date().toISOString()};

    try {
      const payload = await api(`/missions/${encodeURIComponent(missionId)}/${decision}`, {method: 'POST', body: '{}'}, ACTION_TIMEOUT_MS);
      actionInProgress = false;
      const remaining = await load();
      if (remaining.some(item => item.missionId === missionId)) {
        throw new Error('Server returned success but the mission is still awaiting approval.');
      }
      window.__MITIGATE_APPROVAL_LAST_RESULT__ = {missionId, decision, state: 'confirmed', payload, at: new Date().toISOString()};
    } catch (error) {
      actionInProgress = false;
      window.__MITIGATE_APPROVAL_LAST_RESULT__ = {missionId, decision, state: 'failed', error: String(error?.message || error), at: new Date().toISOString()};
      if (resultEl) {
        resultEl.className = 'mitigate-result mitigate-error';
        resultEl.textContent = `${decision === 'approve' ? 'Approval' : 'Rejection'} failed: ${error.message}`;
      }
      buttons.forEach(item => { item.disabled = false; });
      const approve = card?.querySelector('[data-approve]');
      const reject = card?.querySelector('[data-reject]');
      if (approve) approve.textContent = 'Approve & Merge';
      if (reject) reject.textContent = 'Reject';
    }
  }

  launcher.addEventListener('click', () => {
    drawer.classList.toggle('open');
    if (drawer.classList.contains('open')) load();
  });
  closeEl.addEventListener('click', () => drawer.classList.remove('open'));
  refreshEl.addEventListener('click', load);

  load();
  window.setInterval(load, POLL_MS);
})();
