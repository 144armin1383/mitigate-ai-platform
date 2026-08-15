(() => {
  'use strict';

  const ROOT_ID = 'mitigate-opencode-zen-card';
  const PROFILE = 'opencode';
  const BASE_URL = 'https://opencode.ai/zen/v1';
  const DEFAULT_MODEL = 'openai/glm-5.2';
  const SETTINGS_PATH = '/canvas/settings/llm';

  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

  function onLlmSettingsPage() {
    return window.location.pathname.startsWith(SETTINGS_PATH);
  }

  async function jsonRequest(url, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(url, {
        credentials: 'same-origin',
        cache: 'no-store',
        ...options,
        signal: controller.signal,
      });
      let payload = null;
      try {
        payload = await response.json();
      } catch (_) {
        payload = null;
      }
      if (!response.ok) {
        const detail = payload?.error?.message || payload?.detail || `HTTP ${response.status}`;
        throw new Error(detail);
      }
      return payload;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function normalizeModelForZen(model) {
    const value = String(model || '').trim();
    return value.startsWith('openai/') ? value.slice('openai/'.length) : value;
  }

  function setStatus(text, ok = null) {
    const el = document.querySelector(`#${ROOT_ID} [data-status]`);
    if (!el) return;
    el.textContent = text;
    el.style.color = ok === true ? '#62c97b' : ok === false ? '#ff7a7a' : '#b7b7b7';
  }

  async function testConnection() {
    const keyInput = document.querySelector(`#${ROOT_ID} [data-api-key]`);
    const modelInput = document.querySelector(`#${ROOT_ID} [data-model]`);
    const key = String(keyInput?.value || '').trim();
    const model = normalizeModelForZen(modelInput?.value);
    if (!key) {
      setStatus('Enter the OpenCode Zen API key first.', false);
      keyInput?.focus();
      return;
    }
    setStatus('Testing OpenCode Zen…');
    try {
      const result = await jsonRequest('/mitigate-llm/opencode/models', {
        headers: { 'X-Mitigate-LLM-Key': key },
      });
      const ids = Array.isArray(result?.data)
        ? result.data.map((item) => String(item?.id || '')).filter(Boolean)
        : [];
      if (model && ids.length && !ids.includes(model)) {
        throw new Error(`Connected, but model ${model} is not enabled for this workspace.`);
      }
      setStatus(`Connection OK${model ? ` — ${model} available` : ''}.`, true);
    } catch (error) {
      setStatus(`Connection failed: ${error?.message || error}`, false);
    }
  }

  async function saveAndActivate() {
    const keyInput = document.querySelector(`#${ROOT_ID} [data-api-key]`);
    const modelInput = document.querySelector(`#${ROOT_ID} [data-model]`);
    const saveButton = document.querySelector(`#${ROOT_ID} [data-save]`);
    const key = String(keyInput?.value || '').trim();
    const model = String(modelInput?.value || '').trim() || DEFAULT_MODEL;
    if (!key) {
      setStatus('Enter the OpenCode Zen API key first.', false);
      keyInput?.focus();
      return;
    }

    saveButton.disabled = true;
    setStatus('Saving encrypted profile and activating it…');
    try {
      await jsonRequest(`/api/profiles/${encodeURIComponent(PROFILE)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm: {
            model,
            api_key: key,
            base_url: BASE_URL,
            auth_type: 'api_key',
          },
          include_secrets: true,
        }),
      });
      await jsonRequest(`/api/profiles/${encodeURIComponent(PROFILE)}/activate`, {
        method: 'POST',
        body: '',
      });
      const profiles = await jsonRequest('/api/profiles');
      const match = (profiles?.profiles || []).find((item) => item?.name === PROFILE);
      if (profiles?.active_profile !== PROFILE) {
        throw new Error('Profile saved but Agent Canvas did not activate it.');
      }
      if (match && match.api_key_set === false) {
        throw new Error('Profile saved without an API key.');
      }
      keyInput.value = '';
      keyInput.placeholder = 'Configured — paste a new key only to replace it';
      setStatus(`OpenCode Zen active — ${model}. Start a new chat to use it.`, true);
      window.dispatchEvent(new CustomEvent('mitigate-llm-profile-updated', {
        detail: { profile: PROFILE, model, baseUrl: BASE_URL },
      }));
    } catch (error) {
      setStatus(`Save failed: ${error?.message || error}`, false);
    } finally {
      saveButton.disabled = false;
    }
  }

  function render() {
    if (!onLlmSettingsPage()) {
      document.getElementById(ROOT_ID)?.remove();
      return;
    }
    if (document.getElementById(ROOT_ID)) return;

    const root = document.createElement('section');
    root.id = ROOT_ID;
    root.setAttribute('aria-label', 'MITIGATE OpenCode Zen');
    root.innerHTML = `
      <div class="mitigate-opencode-title">MITIGATE · OpenCode Zen</div>
      <div class="mitigate-opencode-help">Manage the OpenCode Zen profile here. The API key is saved by Agent Canvas secret storage and is never written to Git.</div>
      <label>Base URL</label>
      <input value="${esc(BASE_URL)}" readonly aria-readonly="true" />
      <label>Model</label>
      <input data-model value="${esc(DEFAULT_MODEL)}" autocomplete="off" spellcheck="false" />
      <label>API Key</label>
      <input data-api-key type="password" autocomplete="new-password" placeholder="sk-…" />
      <div class="mitigate-opencode-actions">
        <button type="button" data-test>Test Connection</button>
        <button type="button" data-save>Save & Activate</button>
      </div>
      <div data-status class="mitigate-opencode-status">Use a new API key here; existing secrets are never read back into the browser.</div>
    `;

    const style = document.createElement('style');
    style.textContent = `
      #${ROOT_ID}{position:fixed;right:24px;bottom:24px;z-index:2147483000;width:min(420px,calc(100vw - 48px));padding:16px;border:1px solid #3a3a3a;border-radius:12px;background:#171717;color:#f2f2f2;box-shadow:0 16px 45px rgba(0,0,0,.38);font:13px/1.4 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
      #${ROOT_ID} .mitigate-opencode-title{font-size:15px;font-weight:700;margin-bottom:5px}
      #${ROOT_ID} .mitigate-opencode-help{color:#aaa;margin-bottom:12px}
      #${ROOT_ID} label{display:block;color:#d5d5d5;margin:9px 0 5px}
      #${ROOT_ID} input{box-sizing:border-box;width:100%;border:1px solid #444;border-radius:7px;background:#222;color:#fff;padding:9px 10px;outline:none}
      #${ROOT_ID} input:focus{border-color:#777}
      #${ROOT_ID} input[readonly]{color:#aaa}
      #${ROOT_ID} .mitigate-opencode-actions{display:flex;gap:8px;margin-top:13px}
      #${ROOT_ID} button{border:1px solid #555;border-radius:7px;background:#292929;color:#fff;padding:8px 11px;cursor:pointer}
      #${ROOT_ID} button[data-save]{background:#f0d85a;color:#111;border-color:#f0d85a;font-weight:700}
      #${ROOT_ID} button:disabled{opacity:.55;cursor:wait}
      #${ROOT_ID} .mitigate-opencode-status{margin-top:10px;color:#b7b7b7;min-height:18px}
    `;
    root.appendChild(style);
    document.body.appendChild(root);
    root.querySelector('[data-test]').addEventListener('click', testConnection);
    root.querySelector('[data-save]').addEventListener('click', saveAndActivate);
  }

  const observer = new MutationObserver(render);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener('popstate', render);
  window.addEventListener('hashchange', render);
  window.setInterval(render, 1000);
  render();
})();
