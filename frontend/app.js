const API = window.SCRAPER_API_BASE || `http://${window.location.hostname || 'localhost'}:8080`;

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html) e.innerHTML = html;
  return e;
};

function toast(msg, duration = 3000) {
  const tc = document.getElementById('toast-container');
  const t = el('div', 'toast', msg);
  tc.appendChild(t);
  setTimeout(() => t.remove(), duration);
}

function fmt(n) {
  if (n == null) return 'N/A';
  if (Math.abs(n) >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
  if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
  if (Math.abs(n) >= 1e3) return '$' + (n / 1e3).toFixed(2) + 'K';
  return '$' + n.toLocaleString(undefined, { maximumFractionDigits: 6 });
}

function fmtPct(n) {
  if (n == null) return 'N/A';
  const cls = n >= 0 ? 'positive' : 'negative';
  return `<span class="stat-value ${cls}">${n >= 0 ? '+' : ''}${n.toFixed(2)}%</span>`;
}

function signalBadgeClass(signal) {
  const s = (signal || '').toLowerCase().replace(' ', '-');
  if (s.includes('strong-buy')) return 'badge-strong-buy';
  if (s.includes('buy')) return 'badge-buy';
  if (s.includes('strong-short')) return 'badge-strong-sell';
  if (s === 'short') return 'badge-sell';
  if (s.includes('strong-sell')) return 'badge-strong-sell';
  if (s.includes('sell')) return 'badge-sell';
  return 'badge-hold';
}

function loader(text = 'Searching...') {
  return `<div class="loader"><div class="spinner"></div>${text}</div>`;
}

function emptyState(text) {
  return `<div class="empty-state"><p>${text}</p></div>`;
}

async function apiFetch(path, options = {}) {
  const resp = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || resp.statusText);
  }
  return resp.json();
}

function initNav() {
  $$('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      $$('.nav-item').forEach(n => n.classList.remove('active'));
      $$('.panel').forEach(p => p.classList.remove('active'));
      item.classList.add('active');
      const target = item.dataset.panel;
      const panel = document.getElementById('panel-' + target);
      if (panel) {
        panel.classList.add('active');
        $('#topbar-title').textContent = item.querySelector('.label').textContent;
      }
    });
  });
}

async function checkHealth() {
  const dot = $('#status-dot');
  const text = $('#status-text');
  try {
    const data = await apiFetch('/api/v1/health');
    dot.className = 'status-dot';
    text.textContent = data.python_service === 'connected' ? 'All systems online' : 'Python AI disconnected';
    if (data.python_service !== 'connected') dot.className = 'status-dot offline';
  } catch {
    dot.className = 'status-dot offline';
    text.textContent = 'Go server offline';
  }
}
setInterval(checkHealth, 15000);

function initQuery() {
  const form = $('#query-form');
  const input = $('#query-input');
  const results = $('#query-results');

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    results.innerHTML = loader('Searching and synthesizing answer...');
    try {
      const data = await apiFetch('/api/v1/query', {
        method: 'POST',
        body: JSON.stringify({ query: q, max_results: 5 }),
      });
      renderQuery(data, results);
    } catch (err) {
      results.innerHTML = `<div class="card" style="border-color:#da3633">${err.message}</div>`;
    }
  });
}

function renderQuery(data, container) {
  const confColor = { high: '#3fb950', medium: '#d29922', low: '#f85149', none: '#8b949e' }[data.confidence] || '#8b949e';
  let html = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
      <span style="font-size:13px;color:var(--text-muted)">Query:</span>
      <strong>${data.query}</strong>
      <span style="margin-left:auto;font-size:12px;color:${confColor}">${data.confidence} confidence</span>
      <span style="font-size:12px;color:var(--text-dim)">${data.duration_ms}ms</span>
    </div>
    <div class="answer-box">${data.answer}</div>`;

  if (data.sources && data.sources.length) {
    html += '<div class="sources-bar">';
    data.sources.forEach(s => {
      html += `<a class="source-chip" href="${s.url}" target="_blank" rel="noopener">[${s.id}] ${s.title}</a>`;
    });
    html += '</div>';
  }
  container.innerHTML = html;
}

function initNews() {
  const form = $('#news-form');
  const results = $('#news-results');

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const topic = $('#news-input').value.trim();
    const timeframe = $('#news-timeframe').value;
    const limit = parseInt($('#news-limit').value) || 9;
    if (!topic) return;

    results.innerHTML = loader('Fetching latest news...');
    try {
      const data = await apiFetch('/api/v1/news', {
        method: 'POST',
        body: JSON.stringify({ topic, timeframe, limit }),
      });
      renderNews(data, results);
    } catch (err) {
      results.innerHTML = `<div class="card" style="border-color:#da3633">${err.message}</div>`;
    }
  });
}

function renderNews(data, container) {
  if (!data.articles || data.articles.length === 0) {
    container.innerHTML = emptyState(`No news articles found for "${data.topic}"`);
    return;
  }
  let html = `<p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">Found <strong>${data.count}</strong> articles for <strong>${data.topic}</strong></p>`;
  html += '<div class="card-grid">';
  data.articles.forEach(art => {
    const imgTag = art.image
      ? `<img class="news-image" src="${art.image}" alt="" onerror="this.style.display='none'">`
      : '';
    const date = art.published_date ? new Date(art.published_date).toLocaleDateString() : '';
    html += `
      <div class="news-card">
        ${imgTag}
        <div class="news-card-body">
          <div class="news-card-meta">
            <span class="badge badge-news">${art.source || 'News'}</span>
            ${date ? `<span style="margin-left:8px">${date}</span>` : ''}
          </div>
          <div class="news-card-title"><a href="${art.url}" target="_blank" rel="noopener">${art.title}</a></div>
          <div class="news-card-summary">${art.summary || ''}</div>
        </div>
      </div>`;
  });
  html += '</div>';
  container.innerHTML = html;
}

function initScraper() {
  const urlInput = $('#url-input-field');
  const tagContainer = $('#url-tags');
  const scrapeBtn = $('#scrape-btn');
  const results = $('#scrape-results');
  let urls = [];

  function addUrl(url) {
    url = url.trim();
    if (!url) return;
    if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) url = 'https://' + url;
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      toast('Enter a valid URL, such as https://example.com');
      return;
    }
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname) {
      toast('Only http:// and https:// URLs are supported');
      return;
    }
    url = parsed.href;
    if (urls.includes(url)) return;
    urls.push(url);
    renderTags();
  }
  function removeUrl(url) {
    urls = urls.filter(u => u !== url);
    renderTags();
  }
  function renderTags() {
    tagContainer.innerHTML = urls.map(u =>
      `<span class="url-tag">${u}<button onclick="removeUrlTag('${u}')">&times;</button></span>`
    ).join('') + `<input id="url-input-field" type="text" placeholder="Paste a URL and press Enter...">`;
    const inp = tagContainer.querySelector('input');
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); addUrl(inp.value); inp.value = ''; }
    });
    inp.focus();
  }
  window.removeUrlTag = removeUrl;

  urlInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); addUrl(urlInput.value); urlInput.value = ''; }
  });

  scrapeBtn.addEventListener('click', async () => {
    if (urls.length === 0) { toast('Add at least one URL'); return; }
    results.innerHTML = loader(`Scraping ${urls.length} page(s)...`);
    scrapeBtn.disabled = true;
    try {
      const data = await apiFetch('/api/v1/scrape', {
        method: 'POST',
        body: JSON.stringify({ urls, concurrency: 5 }),
      });
      renderScrape(data, results);
    } catch (err) {
      results.innerHTML = `<div class="card" style="border-color:#da3633">${err.message}</div>`;
    } finally {
      scrapeBtn.disabled = false;
    }
  });
}

function renderScrape(data, container) {
  if (!data.results || data.results.length === 0) {
    container.innerHTML = emptyState('No results returned.');
    return;
  }
  let html = `<p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">Scraped <strong>${data.count}</strong> pages</p>`;
  data.results.forEach(r => {
    const statusColor = r.status_code >= 400 ? '#f85149' : r.status_code >= 300 ? '#d29922' : '#3fb950';
    html += `
      <div class="card">
        <div class="card-title">${r.title || 'Untitled'}</div>
        <div class="card-meta">
          <span style="color:${statusColor}">HTTP ${r.status_code}</span> &middot;
          <span>${r.duration_ms}ms</span> &middot;
          <a href="${r.url}" target="_blank" class="card-link">${r.url}</a>
        </div>
        ${r.error ? `<div style="color:#f85149;font-size:13px">Error: ${r.error}</div>` : ''}
        ${r.description ? `<div class="card-body" style="margin-bottom:8px">${r.description}</div>` : ''}
        ${r.clean_text ? `<div class="card-body" style="max-height:160px;overflow:hidden;position:relative">${r.clean_text.slice(0, 600)}${r.clean_text.length > 600 ? '...' : ''}</div>` : ''}
      </div>`;
  });
  container.innerHTML = html;
}

let chatSessionId = 'session-' + Math.random().toString(36).slice(2, 9);

function initChat() {
  const input = $('#chat-input');
  const sendBtn = $('#chat-send');
  const clearBtn = $('#chat-clear');
  const messages = $('#chat-messages');

  function sendMessage() {
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    appendBubble('user', msg, messages);
    const typing = el('div', 'typing-indicator');
    typing.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    messages.appendChild(typing);
    messages.scrollTop = messages.scrollHeight;

    const mode = $('#chat-mode').value;
    const ctx = $('#chat-site-context').value;

    apiFetch('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: msg,
        session_id: chatSessionId,
        mode,
        site_context: ctx,
      }),
    }).then(data => {
      typing.remove();
      appendBubble('bot', data.reply, messages, data.sources);
    }).catch(err => {
      typing.remove();
      appendBubble('bot', 'Error: ' + err.message, messages);
    });
  }

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  clearBtn.addEventListener('click', async () => {
    await apiFetch('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify({ message: '/clear', session_id: chatSessionId }),
    }).catch(() => {});
    chatSessionId = 'session-' + Math.random().toString(36).slice(2, 9);
    messages.innerHTML = '';
    appendBubble('bot', 'Chat session reset.', messages);
  });

  appendBubble('bot', 'Hello. I can search web sources, check crypto signals, assist with site navigation, and scrape web pages. How can I help?', messages);
}

function appendBubble(role, text, container, sources) {
  const b = el('div', `bubble ${role}`);
  b.innerHTML = text.replace(/\n/g, '<br>');
  if (sources && sources.length) {
    const s = el('div', 'sources');
    s.innerHTML = 'Sources: ' + sources.map(src => `<a href="${src.url}" target="_blank">${src.title}</a>`).join(' &middot; ');
    b.appendChild(s);
  }
  container.appendChild(b);
  container.scrollTop = container.scrollHeight;
}

let coinMonitorTimer = null;
let coinMonitorDeadline = 0;
let coinMonitorSymbol = '';

function initCrypto() {
  const form = $('#crypto-form');
  const input = $('#crypto-input');
  const results = $('#crypto-results');

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const coin = input.value.trim();
    if (!coin) return;
    results.innerHTML = loader(`Fetching data for ${coin}...`);
    try {
      const data = await apiFetch('/api/v1/crypto', {
        method: 'POST',
        body: JSON.stringify({ coin }),
      });
      renderCoinCard(data, results);
    } catch (err) {
      results.innerHTML = `<div class="card" style="border-color:#da3633">${err.message}</div>`;
    }
  });

  $$('.quick-coin').forEach(btn => {
    btn.addEventListener('click', () => {
      input.value = btn.dataset.coin;
      form.dispatchEvent(new Event('submit'));
    });
  });

  const watchInput = $('#watch-coin-input');
  const watchBtn = $('#watch-coin-btn');
  const stopBtn = $('#watch-coin-stop');
  const watchStatus = $('#watch-coin-status');
  const watchResults = $('#watch-coin-results');

  const stopCoinMonitor = () => {
    if (coinMonitorTimer) clearInterval(coinMonitorTimer);
    coinMonitorTimer = null;
    coinMonitorDeadline = 0;
    coinMonitorSymbol = '';
    if (watchStatus) watchStatus.textContent = 'Idle';
  };

  const updateWatchStatus = () => {
    if (!coinMonitorDeadline) {
      if (watchStatus) watchStatus.textContent = 'Idle';
      return;
    }
    const remaining = Math.max(0, coinMonitorDeadline - Date.now());
    const secs = Math.ceil(remaining / 1000);
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    if (watchStatus) watchStatus.textContent = `Monitoring ${coinMonitorSymbol} • ${mins}m ${rem}s left`;
    if (remaining <= 0) {
      stopCoinMonitor();
      if (watchResults) {
        watchResults.innerHTML = `<div class="card" style="border-color:#d29922">Monitoring window finished for ${coinMonitorSymbol.toUpperCase()}. Refresh to start a new watch.</div>`;
      }
    }
  };

  const refreshCoinMonitor = async () => {
    if (!coinMonitorSymbol) return;
    const output = $('#watch-coin-results');
    output.innerHTML = loader(`Monitoring ${coinMonitorSymbol}...`);
    try {
      const data = await apiFetch('/api/v1/crypto', {
        method: 'POST',
        body: JSON.stringify({ coin: coinMonitorSymbol }),
      });
      renderCoinCard(data, output);
      if (data.futures_setup) {
        const badge = document.querySelector('#watch-coin-results .direction-badge');
        if (badge) badge.textContent = (data.futures_setup.direction || 'SHORT').toUpperCase();
      }
    } catch (err) {
      output.innerHTML = `<div class="card" style="border-color:#da3633">${err.message}</div>`;
    }
    updateWatchStatus();
  };

  watchBtn.addEventListener('click', async () => {
    const coin = (watchInput.value || '').trim();
    if (!coin) return;
    coinMonitorSymbol = coin;
    coinMonitorDeadline = Date.now() + 5 * 60 * 1000;
    updateWatchStatus();
    await refreshCoinMonitor();
    if (coinMonitorTimer) clearInterval(coinMonitorTimer);
    coinMonitorTimer = setInterval(refreshCoinMonitor, 15000);
  });

  stopBtn.addEventListener('click', () => {
    stopCoinMonitor();
    if (watchResults) {
      watchResults.innerHTML = `<div class="empty-state"><div class="icon">📈</div><p>Monitor stopped. Enter another coin to start a fresh 5-minute session.</p></div>`;
    }
  });

  initFuturesSignals();
  loadTrending();
}

let futuresRefreshTimer = null;

function isFuturesSignalStale(signal) {
  const price = Number(signal.price ?? 0);
  const entry = Number(signal.entry ?? 0);
  const direction = String(signal.direction || '').toLowerCase();
  const expiresAt = Number(signal.expires_at ?? 0);

  if (expiresAt && Date.now() / 1000 > expiresAt) {
    return true;
  }

  if (!price || !entry) return true;
  if (direction === 'short') return price > entry * 1.008;
  if (direction === 'long') return price < entry * 0.992;
  return false;
}

function initFuturesSignals() {
  const grid = $('#futures-signals-grid');
  const tabs = $$('#futures-strategy-tabs .strategy-tab');
  const refreshBtn = $('#futures-refresh');

  const setActiveTab = (strategy) => {
    tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.strategy === strategy));
    loadFuturesSignals(strategy);
  };

  tabs.forEach(tab => {
    tab.addEventListener('click', () => setActiveTab(tab.dataset.strategy));
  });

  refreshBtn.addEventListener('click', () => {
    const activeStrategy = document.querySelector('.strategy-tab.active')?.dataset.strategy || 'short';
    setActiveTab(activeStrategy);
  });

  if (futuresRefreshTimer) clearInterval(futuresRefreshTimer);
  futuresRefreshTimer = setInterval(() => {
    const activeStrategy = document.querySelector('.strategy-tab.active')?.dataset.strategy || 'short';
    setActiveTab(activeStrategy);
  }, 15000);

  if (grid) {
    setActiveTab('short');
  }
}

async function loadFuturesSignals(strategy = 'short') {
  const container = $('#futures-signals-grid');
  if (!container) return;

  container.innerHTML = loader(`Loading ${strategy} setups...`);
  try {
    const data = await apiFetch(`/api/v1/crypto/futures-signals?strategy=${encodeURIComponent(strategy)}&limit=6&min_volume=15000000`);
    const filtered = (data.signals || []).filter(signal => !isFuturesSignalStale(signal));
    renderFuturesSignals({ ...data, signals: filtered }, container);
  } catch (err) {
    container.innerHTML = `<div class="card" style="border-color:#da3633">${err.message}</div>`;
  }
}

function getVolatilityStatus(signal) {
  const price = Number(signal.price ?? 0);
  const high = Number(signal.high_24h ?? 0);
  const low = Number(signal.low_24h ?? 0);
  const explicit = (signal.volatility || '').toLowerCase();
  if (explicit) {
    const className = explicit === 'volatile' ? 'volatile' : explicit === 'stable' ? 'stable' : explicit === 'moderate' ? 'moderate' : 'unknown';
    const label = explicit === 'unknown' ? 'Volatility unavailable' : explicit.charAt(0).toUpperCase() + explicit.slice(1);
    return {
      label,
      className,
      pct: Number(signal.volatility_pct ?? 0).toFixed(2),
    };
  }

  if (!price || !high || !low) {
    return { label: 'Volatility unavailable', className: 'unknown', pct: '0.00' };
  }

  const pct = ((high - low) / price) * 100;
  const status = pct >= 4 ? 'Volatile' : pct > 2 ? 'Moderate' : 'Stable';
  const className = pct >= 4 ? 'volatile' : pct > 2 ? 'moderate' : 'stable';
  return { label: status, className, pct: pct.toFixed(2) };
}

function renderFuturesSignals(data, container) {
  if (!data || !Array.isArray(data.signals) || data.signals.length === 0) {
    container.innerHTML = emptyState('No candidates found for this strategy. Try the other direction or lower the volume filter.');
    return;
  }

  container.innerHTML = data.signals.map(signal => {
    const direction = (signal.direction || 'short').toUpperCase();
    const directionClass = direction === 'LONG' ? 'positive' : 'negative';
    const entry = signal.entry ?? signal.price ?? 0;
    const rationale = signal.rationale || `${signal.symbol} is trading near the ${direction === 'SHORT' ? 'upper' : 'lower'} range and is filtering for a ${direction.toLowerCase()} setup.`;
    const volatility = getVolatilityStatus(signal);
    const dyorWarning = volatility.className === 'volatile' ? '<span class="dyor-pill">DYOR before trading</span>' : '';
    const statusLabel = signal.signal_status === 'confirmed' ? 'Confirmed' : 'Provisional';
    const statusClass = signal.signal_status === 'confirmed' ? 'stable' : 'moderate';

    return `
      <div class="futures-card">
        <div class="futures-header">
          <div>
            <div class="futures-symbol">${signal.symbol}</div>
            <div class="futures-subtitle">${signal.base || signal.symbol.replace('USDT', '')} • ${signal.change_pct >= 0 ? '+' : ''}${Number(signal.change_pct || 0).toFixed(2)}%</div>
          </div>
          <span class="direction-badge ${directionClass}">${direction}</span>
        </div>

        <div class="futures-metric-grid">
          <div class="futures-metric"><span>Entry</span><strong>$${Number(entry).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div class="futures-metric"><span>TP1</span><strong>$${Number(signal.tp1 || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div class="futures-metric"><span>TP2</span><strong>$${Number(signal.tp2 || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div class="futures-metric"><span>TP3</span><strong>$${Number(signal.tp3 || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div class="futures-metric"><span>SL</span><strong>$${Number(signal.sl || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div class="futures-metric"><span>R:R</span><strong>${Number(signal.rr || 0).toFixed(2)} : 1</strong></div>
          <div class="futures-metric"><span>Leverage</span><strong>${Number(signal.leverage || 0)}x</strong></div>
          <div class="futures-metric"><span>Vol</span><strong>$${Number(signal.volume_usdt || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</strong></div>
        </div>

        <div class="futures-footer">
          <span class="rr-pill">${Number(signal.rr || 0).toFixed(2)} R:R</span>
          <span class="vol-pill ${statusClass}">${statusLabel} • ${Number(signal.confidence_pct || 0).toFixed(0)}% confidence</span>
          <span class="lev-pill">${Number(signal.leverage || 0)}x Leverage</span>
          <span class="vol-pill ${volatility.className}">${volatility.label} • ${volatility.pct}%</span>
          ${dyorWarning}
        </div>

        <div class="futures-rationale">${signal.risk_warning || rationale}</div>
      </div>
    `;
  }).join('');
}

async function loadTrending() {
  const container = $('#trending-list');
  container.innerHTML = loader('Loading trending...');
  try {
    const data = await apiFetch('/api/v1/crypto/trending');
    if (!data.trending || data.trending.length === 0) {
      container.innerHTML = '<span style="color:var(--text-muted);font-size:13px">No data</span>';
      return;
    }
    container.innerHTML = '';
    data.trending.forEach(coin => {
      const pill = el('div', 'trending-pill');
      pill.innerHTML = `${coin.image ? `<img src="${coin.image}" alt="">` : ''}${coin.symbol} <span style="color:var(--text-muted);font-size:11px">#${coin.market_cap_rank || '-'}</span>`;
      pill.addEventListener('click', () => {
        document.getElementById('crypto-input').value = coin.id;
        document.getElementById('crypto-form').dispatchEvent(new Event('submit'));
      });
      container.appendChild(pill);
    });
  } catch {
    container.innerHTML = '<span style="color:var(--text-muted);font-size:13px">Could not load trending</span>';
  }
}

function renderCoinCard(d, container) {
  const badgeClass = signalBadgeClass(d.signal);
  const volatilityLabel = d?.futures_setup ? ((d.futures_setup.volatility || 'unknown').toLowerCase() === 'unknown' ? 'Volatility unavailable' : (d.futures_setup.volatility || 'Unknown').charAt(0).toUpperCase() + (d.futures_setup.volatility || 'Unknown').slice(1)) : 'Volatility unavailable';
  const volatilityClass = d?.futures_setup ? ((d.futures_setup.volatility || 'unknown').toLowerCase() === 'volatile' ? 'volatile' : (d.futures_setup.volatility || 'unknown').toLowerCase() === 'stable' ? 'stable' : (d.futures_setup.volatility || 'unknown').toLowerCase() === 'moderate' ? 'moderate' : 'unknown') : 'unknown';
  const volatilityPct = d?.futures_setup ? Number(d.futures_setup.volatility_pct ?? 0).toFixed(2) : '0.00';
  const dyorWarning = volatilityClass === 'volatile' ? '<span class="dyor-pill">DYOR before trading</span>' : '';
  const priceDisplay = d.price_usd >= 0.01
    ? '$' + d.price_usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })
    : '$' + d.price_usd.toFixed(8);

  let futuresMarkup = '';
  if (d.futures_setup) {
    const s = d.futures_setup;
    const vol = (s.volatility || '').toLowerCase();
    const volLabel = vol === 'unknown' ? 'Volatility unavailable' : (vol.charAt(0).toUpperCase() + vol.slice(1));
    const volClass = vol === 'volatile' ? 'volatile' : vol === 'stable' ? 'stable' : vol === 'moderate' ? 'moderate' : 'unknown';
    const volPct = Number(s.volatility_pct ?? 0).toFixed(2);
    futuresMarkup = `
      <div class="trade-setup-box">
        <div class="trade-setup-header">
          <span class="direction-badge ${s.direction === 'long' ? 'positive' : 'negative'}">${(s.direction || 'SHORT').toUpperCase()}</span>
          <span class="trade-setup-symbol">${s.symbol}</span>
        </div>
        <div class="trade-setup-grid">
          <div><span>Entry</span><strong>$${Number(s.entry || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div><span>TP1</span><strong>$${Number(s.tp1 || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div><span>TP2</span><strong>$${Number(s.tp2 || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div><span>TP3</span><strong>$${Number(s.tp3 || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div><span>SL</span><strong>$${Number(s.sl || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}</strong></div>
          <div><span>R:R</span><strong>${Number(s.risk_reward || 0).toFixed(2)} : 1</strong></div>
          <div><span>Leverage</span><strong>${Number(s.leverage || 0)}x</strong></div>
          <div><span>Risk</span><strong>${Number(s.risk_pct || 0).toFixed(2)}%</strong></div>
        </div>
        <div class="trade-setup-inline-meta">
          <span class="vol-pill ${volClass}">${volLabel} • ${volPct}%</span>
        </div>
        <div class="trade-rationale">${s.rationale || 'Trade setup generated from Binance futures range and volume.'}</div>
      </div>
    `;
  }

  container.innerHTML = `
    <div class="crypto-card">
      <div class="crypto-header">
        ${d.image ? `<img class="crypto-icon" src="${d.image}" alt="">` : ''}
        <div>
          <div class="crypto-name">${d.name} <span class="crypto-symbol">${d.symbol}</span></div>
          <div style="margin-top:4px; display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
            <span class="badge ${badgeClass}">${d.signal}</span>
            ${d.signal_confidence != null ? `<span style="font-size:11px;color:var(--text-muted)">${Number(d.signal_confidence).toFixed(0)}% multi-factor confidence</span>` : ''}
            <span class="vol-pill ${volatilityClass}">${volatilityLabel} • ${volatilityPct}%</span>
            ${dyorWarning}
          </div>
        </div>
        <div style="margin-left:auto;text-align:right">
          <div class="crypto-price">${priceDisplay}</div>
          <div style="font-size:13px">24h: ${fmtPct(d.change_24h_pct)}</div>
        </div>
      </div>

      <div class="crypto-stats">
        <div class="stat-box">
          <div class="stat-label">1h Change</div>
          <div>${fmtPct(d.change_1h_pct)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">7d Change</div>
          <div>${fmtPct(d.change_7d_pct)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">24h High</div>
          <div class="stat-value">${fmt(d.high_24h_usd)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">24h Low</div>
          <div class="stat-value">${fmt(d.low_24h_usd)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Market Cap</div>
          <div class="stat-value">${fmt(d.market_cap_usd)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Volume 24h</div>
          <div class="stat-value">${fmt(d.volume_24h_usd)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">All-Time High</div>
          <div class="stat-value">${fmt(d.ath_usd)}</div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Momentum Score</div>
          <div class="stat-value ${d.momentum_score >= 0 ? 'positive' : 'negative'}">${d.momentum_score}</div>
        </div>
      </div>

      ${futuresMarkup}
      <div class="disclaimer">${d.disclaimer}</div>
    </div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  initNav();
  checkHealth();
  initQuery();
  initNews();
  initScraper();
  initChat();
  initCrypto();
  $$('.nav-item')[0]?.click();
});
