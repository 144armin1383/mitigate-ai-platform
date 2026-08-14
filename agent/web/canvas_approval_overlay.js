(() => {
  'use strict';

  if (window.__MITIGATE_APPROVAL_OVERLAY__) return;
  window.__MITIGATE_APPROVAL_OVERLAY__ = true;

  const API_BASE = '/mitigate-runtime/api';
  const POLL_MS = 5000;

  const css = `
    #mitigate-approval-launcher{position:fixed;left:16px;bottom:118px;z-index:2147483600;border:1px solid rgba(255,255,255,.14);background:#151922;color:#f4f7ff;border-radius:12px;padding:10px 12px;font:600 13px/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.35);cursor:pointer;display:flex;align-items:center;gap:8px}
    #mitigate-approval-launcher:hover{background:#1c2230}
    #mitigate-approval-count{min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:#f2b84b;color:#171106;display:inline-flex;align-items:center;justify-content:center;font-size:11px;font-weight:800}
    #mitigate-approval-drawer{position:fixed;left:16px;bottom:164px;z-index:2147483601;width:min(420px,calc(100vw - 32px));max-height:min(620px,calc(100vh - 196px));overflow:auto;background:#0f1420;color:#edf2ff;border:1px solid rgba(255,255,255,.14);border-radius:14px;box-shadow:0 16px 50px rgba(0,0,0,.5);font:13px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:none}
    #mitigate-approval-drawer.open{display:block}
    .mitigate-approval-head{position:sticky;top:0;background:#0f1420;border-bottom:1px solid rgba(255,255,255,.1);padding:14px 14px 12px;display:flex;justify-content:space-between;gap:12px;align-items:center}
    .mitigate-approval-title{font-weight:800;font-size:14px}.mitigate-approval-sub{font-size:11px;color:#9aa7be;margin-top:3px}.mitigate-approval-actions{display:flex;gap:6px}.mitigate-mini-btn{border:1px solid rgba(255,255,255,.14);background:#1a2231;color:#e9efff;border-radius:8px;padding:7px 9px;font-weight:700;cursor:pointer}.mitigate-mini-btn:hover{background:#232d3f}.mitigate-approval-body{padding:12px}.mitigate-empty{padding:20px 8px;color:#9aa7be;text-align:center}.mitigate-approval-card{border:1px solid rgba(255,255,255,.11);background:#141b28;border-radius:11px;padding:12px;margin-bottom:10px}.mitigate-approval-card:last-child{margin-bottom:0}.mitigate-row{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.mitigate-id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#b9c7df;overflow-wrap:anywhere}.mitigate-badge{display:inline-flex;border-radius:999px;padding:3px 7px;background:rgba(242,184,75,.15);color:#ffd378;font-size:10px;font-weight:800;white-space:nowrap}.mitigate-reason{color:#a9b5ca;font-size:11px;margin:8px 0}.mitigate-approve-btn{width:100%;border:0;border-radius:9px;background:#3bd09d;color:#07140f;font-weight:850;padding:9px 10px;cursor:pointer}.mitigate-approve-btn:hover{filter:brightness(1.05)}.mitigate-approve-btn:disabled{opacity:.55;cursor:wait}.mitigate-error{color:#ff9ba6;font-size:11px;margin-top:8px}.mitigate-success{color:#6ee7b7;font-size:11px;margin-top:8px}
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

  async function api(path, options = {}) {
    const response = await fetch(API_BASE + path, {
      ...options,
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', ...(options.headers || {})}
    });
    const text = await response.text();
    let payload = {};
    try { payload = JSON.parse(text); } catch (_) {}
    if (!response.ok) {
      const message = payload?.error?.message || payload?.error || `HTTP ${response.status}`;
      throw new Error(message);
    }
    return payload;
  }

  function approvalItems(payload) {
    const data = payload?.data || payload || {};
    const items = Array.isArray(data.items) ? data.items : [];
    return items.flatMap(item => {
      if (item?.status !== 'awaiting_approval') return [];
      const missions = Array.isArray(item.missions) ? item.missions : [];
      return missions.flatMap(entry => {
        const mission = entry?.mission || {};
        if (mission?.state !== 'awaiting_approval' || mission?.requires_action !== 'manual_review' || !mission?.id) return [];
        return [{requestId: item.request_id || '', missionId: mission.id, reason: mission.status_reason || data.status_reason || 'manual_review_required'}];
      });
    });
  }

  function render(items) {
    countEl.textContent = String(items.length);
    countEl.style.background = items.length ? '#f2b84b' : '#344157';
    countEl.style.color = items.length ? '#171106' : '#d7dfef';
    if (!items.length) {
      bodyEl.innerHTML = '<div class="mitigate-empty">No missions are waiting for approval.</div>';
      return;
    }
    bodyEl.innerHTML = items.map(item => `
      <article class="mitigate-approval-card" data-mission="${esc(item.missionId)}">
        <div class="mitigate-row"><div><div class="mitigate-id">${esc(item.requestId)}</div><div class="mitigate-id" style="margin-top:4px">${esc(item.missionId)}</div></div><span class="mitigate-badge">Awaiting Approval</span></div>
        <div class="mitigate-reason">${esc(item.reason)}</div>
        <button class="mitigate-approve-btn" type="button" data-approve="${esc(item.missionId)}">Approve &amp; Merge</button>
        <div class="mitigate-result" aria-live="polite"></div>
      </article>`).join('');
    bodyEl.querySelectorAll('[data-approve]').forEach(button => {
      button.addEventListener('click', () => approve(button));
    });
  }

  async function load() {
    try {
      const payload = await api('/requests?limit=60');
      render(approvalItems(payload));
    } catch (error) {
      bodyEl.innerHTML = `<div class="mitigate-error">Approval API unavailable: ${esc(error.message)}</div>`;
    }
  }

  async function approve(button) {
    const missionId = button.getAttribute('data-approve');
    if (!missionId) return;
    if (!window.confirm(`Approve reviewed mission ${missionId} and fast-forward its verified branch into main?`)) return;
    const card = button.closest('.mitigate-approval-card');
    const resultEl = card?.querySelector('.mitigate-result');
    button.disabled = true;
    button.textContent = 'Approving…';
    if (resultEl) resultEl.textContent = '';
    try {
      await api(`/missions/${encodeURIComponent(missionId)}/approve`, {method: 'POST', body: '{}'});
      if (resultEl) {
        resultEl.className = 'mitigate-result mitigate-success';
        resultEl.textContent = 'Approved and merged successfully.';
      }
      await load();
    } catch (error) {
      if (resultEl) {
        resultEl.className = 'mitigate-result mitigate-error';
        resultEl.textContent = `Approval blocked: ${error.message}`;
      }
      button.disabled = false;
      button.textContent = 'Approve & Merge';
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
