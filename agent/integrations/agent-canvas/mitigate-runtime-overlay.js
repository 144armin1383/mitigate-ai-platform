(() => {
  'use strict';

  if (window.__MITIGATE_RUNTIME_OVERLAY_LOADED__) return;
  window.__MITIGATE_RUNTIME_OVERLAY_LOADED__ = true;

  const API = '/mitigate-runtime/providers';

  const MITIGATE_MCP_CONFIG = {
    'mitigate-runtime': {
      url: 'http://172.18.0.1:8771/mcp',
      transport: 'streamable-http',
      enabled: true
    }
  };

  const nativeFetch = window.fetch.bind(window);

  window.fetch = async function mitigateFetch(
    input,
    init = {}
  ) {
    try {
      const isRequest =
        typeof Request !== 'undefined' &&
        input instanceof Request;

      const url = isRequest
        ? input.url
        : String(input);

      const method = String(
        init.method ||
        (isRequest ? input.method : 'GET')
      ).toUpperCase();

      const isConversationCreate =
        method === 'POST' &&
        /\/api\/conversations(?:\?|$)/.test(url);

      if (isConversationCreate) {
        let bodyText = '';

        if (typeof init.body === 'string') {
          bodyText = init.body;
        } else if (isRequest) {
          bodyText = await input.clone().text();
        }

        if (bodyText) {
          const payload = JSON.parse(bodyText);

          const settingsResponse = await nativeFetch(
            '/api/settings',
            {
              method: 'GET',
              headers: {
                'X-Expose-Secrets': 'encrypted'
              },
              credentials: 'same-origin',
              cache: 'no-store'
            }
          );

          if (!settingsResponse.ok) {
            throw new Error(
              'Unable to obtain encrypted Agent settings'
            );
          }

          const settings =
            await settingsResponse.json();

          const agentSettings = JSON.parse(
            JSON.stringify(
              settings.agent_settings || {}
            )
          );

          delete agentSettings.schema_version;

          agentSettings.mcp_config = {
            ...(agentSettings.mcp_config || {}),
            ...MITIGATE_MCP_CONFIG
          };

          /*
           * Preserve any tool selection explicitly
           * supplied by Agent Canvas.
           */
          if (
            payload.agent &&
            Array.isArray(payload.agent.tools)
          ) {
            agentSettings.tools =
              payload.agent.tools;
          }

          payload.agent_settings =
            agentSettings;

          /*
           * X-Expose-Secrets returns encrypted
           * credentials, never plaintext.
           */
          payload.secrets_encrypted = true;

          /*
           * StartConversationRequest requires these
           * launch modes to be mutually exclusive.
           */
          delete payload.agent;
          delete payload.agent_profile_id;

          const newBody =
            JSON.stringify(payload);

          if (isRequest) {
            input = new Request(
              input,
              {
                body: newBody
              }
            );

            init = {};
          } else {
            init = {
              ...init,
              body: newBody
            };
          }

          console.info(
            '[MITIGATE] Runtime MCP injected ' +
            'into new conversation'
          );
        }
      }
    } catch (error) {
      /*
       * Fail open: never break upstream Canvas
       * if MITIGATE integration has a problem.
       */
      console.error(
        '[MITIGATE] MCP conversation injection failed',
        error
      );
    }

    return nativeFetch(
      input,
      init
    );
  };

  const esc = (v) => String(v ?? '').replace(
    /[&<>"']/g,
    c => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    })[c]
  );

  function styles() {
    if (document.getElementById('mitigate-overlay-style')) return;

    const s = document.createElement('style');
    s.id = 'mitigate-overlay-style';

    s.textContent = `
      #mitigate-runtime-button{
        position:fixed;
        left:18px;
        bottom:72px;
        z-index:2147483000;
        border:1px solid rgba(255,255,255,.14);
        background:#1c1c1c;
        color:#f5f5f5;
        border-radius:10px;
        padding:9px 12px;
        font:600 12px system-ui,sans-serif;
        cursor:pointer;
        box-shadow:0 8px 30px rgba(0,0,0,.35);
        display:flex;
        gap:7px;
        align-items:center
      }
      #mitigate-runtime-button:hover{background:#262626}
      .mit-dot{
        width:8px;
        height:8px;
        border-radius:50%;
        background:#d7bd63
      }
      #mitigate-runtime-backdrop{
        position:fixed;
        inset:0;
        z-index:2147483001;
        background:rgba(0,0,0,.58);
        backdrop-filter:blur(4px);
        display:flex;
        align-items:center;
        justify-content:center;
        padding:24px
      }
      #mitigate-runtime-modal{
        width:min(760px,96vw);
        background:#171717;
        color:#f5f5f5;
        border:1px solid rgba(255,255,255,.14);
        border-radius:16px;
        box-shadow:0 24px 80px rgba(0,0,0,.55);
        font-family:system-ui,sans-serif
      }
      .mit-head{
        padding:20px;
        display:flex;
        justify-content:space-between;
        border-bottom:1px solid rgba(255,255,255,.1)
      }
      .mit-title{font-size:18px;font-weight:750}
      .mit-sub{font-size:11px;color:#999;margin-top:5px}
      .mit-close{
        border:0;
        background:none;
        color:#aaa;
        font-size:24px;
        cursor:pointer
      }
      .mit-body{padding:18px 20px 20px}
      .mit-grid{
        display:grid;
        grid-template-columns:repeat(3,minmax(0,1fr));
        gap:12px
      }
      .mit-card{
        border:1px solid rgba(255,255,255,.1);
        background:#202020;
        border-radius:12px;
        padding:14px
      }
      .mit-name{font-size:14px;font-weight:700}
      .mit-state{
        margin-top:10px;
        font-size:12px;
        font-weight:700
      }
      .mit-state.ok{color:#65d8a5}
      .mit-state.bad{color:#ff8b95}
      .mit-version{margin-top:8px;font-size:11px;color:#aaa}
      .mit-detail{margin-top:5px;font-size:11px;color:#888}
      .mit-actions{
        display:flex;
        justify-content:flex-end;
        gap:9px;
        margin-top:16px
      }
      .mit-btn{
        border:1px solid rgba(255,255,255,.14);
        background:#272727;
        color:#fff;
        border-radius:9px;
        padding:9px 12px;
        cursor:pointer
      }
      .mit-message{
        padding:15px;
        border:1px solid rgba(255,255,255,.1);
        border-radius:10px;
        color:#aaa;
        font-size:12px
      }
      .mit-foot{
        margin-top:14px;
        font-size:10px;
        color:#777
      }
      @media(max-width:720px){
        .mit-grid{grid-template-columns:1fr}
      }
    `;

    document.head.appendChild(s);
  }

  function card(item) {
    const ok =
      Boolean(item.available) &&
      item.functional_probe !== 'failed';

    let detail = 'Runtime probe available';

    if (item.provider === 'openhands') {
      detail = `LLM: ${item.llm_configured ? 'configured' : 'missing'}`;
    } else if (item.functional_probe) {
      detail = `Diagnostic: ${item.functional_probe}`;
    }

    return `
      <div class="mit-card">
        <div class="mit-name">${esc(item.name || item.provider)}</div>
        <div class="mit-state ${ok ? 'ok' : 'bad'}">
          ${ok ? '● Available' : '● Needs attention'}
        </div>
        <div class="mit-version">${esc(item.version || 'Version unavailable')}</div>
        <div class="mit-detail">${esc(detail)}</div>
      </div>
    `;
  }

  async function load(container, deep = false) {
    container.innerHTML =
      `<div class="mit-message">${deep ? 'Running diagnostics…' : 'Checking runtimes…'}</div>`;

    try {
      const response = await fetch(
        API + (deep ? '?deep=1' : ''),
        {
          credentials: 'same-origin',
          cache: 'no-store'
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const items = data.runtimes || [];

      container.innerHTML =
        `<div class="mit-grid">${items.map(card).join('')}</div>`;

      const dot = document.querySelector(
        '#mitigate-runtime-button .mit-dot'
      );

      if (dot) {
        dot.style.background =
          data.ok ? '#65d8a5' : '#ff8b95';
      }
    } catch (error) {
      container.innerHTML =
        `<div class="mit-message">Unable to load runtime status: ${esc(error.message)}</div>`;
    }
  }

  function openModal() {
    if (document.getElementById('mitigate-runtime-backdrop')) return;

    const backdrop = document.createElement('div');
    backdrop.id = 'mitigate-runtime-backdrop';

    backdrop.innerHTML = `
      <section id="mitigate-runtime-modal">
        <div class="mit-head">
          <div>
            <div class="mit-title">MITIGATE AI Runtimes</div>
            <div class="mit-sub">
              OpenHands · OpenClaw · Ruflo
            </div>
          </div>
          <button class="mit-close">×</button>
        </div>

        <div class="mit-body">
          <div id="mitigate-runtime-cards"></div>

          <div class="mit-actions">
            <button class="mit-btn" id="mitigate-runtime-refresh">
              Refresh
            </button>
            <button class="mit-btn" id="mitigate-runtime-diagnostics">
              Run diagnostics
            </button>
          </div>

          <div class="mit-foot">
            Integration: external MITIGATE overlay.
            Official Agent Canvas files are untouched.
          </div>
        </div>
      </section>
    `;

    document.body.appendChild(backdrop);

    const close = () => backdrop.remove();

    backdrop.querySelector('.mit-close').onclick = close;

    backdrop.onclick = (event) => {
      if (event.target === backdrop) close();
    };

    const cards = backdrop.querySelector(
      '#mitigate-runtime-cards'
    );

    backdrop.querySelector(
      '#mitigate-runtime-refresh'
    ).onclick = () => load(cards, false);

    backdrop.querySelector(
      '#mitigate-runtime-diagnostics'
    ).onclick = () => load(cards, true);

    load(cards, false);
  }

  function mount() {
    if (!document.body) return;
    if (document.getElementById('mitigate-runtime-button')) return;

    styles();

    const button = document.createElement('button');

    button.id = 'mitigate-runtime-button';
    button.innerHTML =
      '<span class="mit-dot"></span><span>MITIGATE Runtimes</span>';

    button.onclick = openModal;

    document.body.appendChild(button);
  }

  if (document.readyState === 'loading') {
    document.addEventListener(
      'DOMContentLoaded',
      mount,
      {once:true}
    );
  } else {
    mount();
  }
})();
