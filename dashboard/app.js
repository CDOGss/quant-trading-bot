// ============================================================
// Trading Bot Dashboard – Paper Trading CAC40
// Fetch portfolio_state.json (publié à côté de index.html sur
// GitHub Pages) et affiche le tableau de bord.
// ============================================================

const STATE_URL = 'portfolio_state.json';
let chart = null;

const css = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function fmtEUR(v) {
    return (Number(v) || 0).toLocaleString('fr-FR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2
    }) + ' €';
}

function fmtPct(v) {
    if (v === null || v === undefined) return '—';
    return (v >= 0 ? '+' : '') + Number(v).toFixed(2) + ' %';
}

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function fmtDateTime(iso) {
    return new Date(iso).toLocaleString('fr-FR', {
        day: '2-digit', month: '2-digit', year: '2-digit',
        hour: '2-digit', minute: '2-digit'
    });
}

function actionClass(a) {
    return a === 'BUY' ? 'action-buy' : a === 'SELL' ? 'action-sell' : 'action-hold';
}

function confBar(conf) {
    const c = Math.max(0, Math.min(1, Number(conf) || 0));
    return `
        <div class="conf-bar">
            <div class="bar"><div class="bar-fill" style="width:${c * 100}%"></div></div>
            <span>${Math.round(c * 100)}%</span>
        </div>`;
}

function emptyRow(cols, text) {
    return `<tr><td colspan="${cols}" style="text-align:center;color:var(--text-muted);">${text}</td></tr>`;
}

function updateStatus(state, ok) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const ts = document.getElementById('timestamp');

    if (ok && state) {
        dot.className = 'dot';
        text.textContent = 'En ligne';
        ts.textContent = `MàJ ${fmtDateTime(state.updated)}`;
    } else {
        dot.className = 'dot error';
        text.textContent = 'Erreur de chargement';
        ts.textContent = '—';
    }
}

function updateStats(state) {
    document.getElementById('equity').textContent = fmtEUR(state.equity);
    document.getElementById('cash').textContent = fmtEUR(state.cash);
    document.getElementById('trades-count').textContent =
        `${(state.trades || []).length} · ${Object.keys(state.holdings || {}).length}`;
    const roi = state.equity / state.initial_capital - 1;
    const roiEl = document.getElementById('roi');
    roiEl.textContent = fmtPct(roi * 100);
    roiEl.style.color = roi >= 0 ? 'var(--accent)' : 'var(--red)';
}

function updatePositions(state) {
    const tbody = document.querySelector('#positions-table tbody');
    const holdings = Object.entries(state.holdings || {});
    if (holdings.length === 0) {
        tbody.innerHTML = emptyRow(5, 'Aucune position ouverte');
        return;
    }
    tbody.innerHTML = holdings.map(([sym, pos]) => {
        const pnlClass = pos.pnl >= 0 ? 'pos-pnl-positive' : 'pos-pnl-negative';
        return `
            <tr>
                <td>${esc(sym)}</td>
                <td>${Number(pos.shares).toFixed(3)}</td>
                <td>${fmtEUR(pos.avg_price)}</td>
                <td>${fmtEUR(pos.market_value)}</td>
                <td class="${pnlClass}">${pos.pnl >= 0 ? '+' : ''}${fmtEUR(pos.pnl)}</td>
            </tr>`;
    }).join('');
}

function updateDecisions(state) {
    const tbody = document.querySelector('#decisions-table tbody');
    const last = state.last_decisions;
    document.getElementById('engine').textContent = state.decision_engine || '';
    document.getElementById('strategy').textContent = last && last.strategy
        ? `${last.strategy} — ${fmtDateTime(last.timestamp)}`
        : '';
    if (!last || !(last.decisions || []).length) {
        tbody.innerHTML = emptyRow(7, 'Pas encore de décision (le bot tourne en semaine pendant la séance)');
        return;
    }
    const prices = state.prices || {};
    tbody.innerHTML = last.decisions.map((d) => {
        const p = prices[d.ticker] || {};
        const retClass = p.ret1d >= 0 ? 'num-pos' : 'num-neg';
        return `
            <tr>
                <td>${esc(d.ticker)}</td>
                <td>${p.last !== undefined ? fmtEUR(p.last) : '—'}</td>
                <td class="${retClass}">${fmtPct(p.ret1d)}</td>
                <td>${p.rsi14 ?? '—'}</td>
                <td class="${actionClass(d.action)}">${esc(d.action)}</td>
                <td>${confBar(d.confidence)}</td>
                <td>${esc(d.reason)}</td>
            </tr>`;
    }).join('');
}

function updateTrades(state) {
    const tbody = document.querySelector('#trades-table tbody');
    const trades = state.trades || [];
    if (trades.length === 0) {
        tbody.innerHTML = emptyRow(7, 'Aucun trade enregistré');
        return;
    }
    // Les 50 plus récents, du plus récent au plus ancien
    tbody.innerHTML = trades.slice(-50).reverse().map((t) => `
        <tr>
            <td>${fmtDateTime(t.timestamp)}</td>
            <td>${esc(t.ticker)}</td>
            <td class="${actionClass(t.action)}">${esc(t.action)}</td>
            <td>${Number(t.shares || 0).toFixed(3)}</td>
            <td>${fmtEUR(t.price)}</td>
            <td>${confBar(t.confidence)}</td>
            <td>${esc(t.reason)}</td>
        </tr>`).join('');
}

function updateChart(state) {
    const history = state.history || [];
    const labels = history.map(h => fmtDateTime(h.timestamp));
    const data = history.map(h => h.equity);

    if (chart) {
        chart.data.labels = labels;
        chart.data.datasets[0].data = data;
        chart.update('none');
        return;
    }
    if (typeof Chart === 'undefined') return;   // CDN indisponible

    const accent = css('--accent');
    const border = css('--border');
    const muted = css('--text-muted');
    chart = new Chart(document.getElementById('capitalChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Capital',
                data,
                borderColor: accent,
                backgroundColor: accent + '22',
                tension: 0.3,
                fill: true,
                borderWidth: 2,
                pointRadius: data.length < 30 ? 3 : 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: { label: ctx => 'Capital : ' + fmtEUR(ctx.parsed.y) }
                }
            },
            scales: {
                x: {
                    grid: { color: border },
                    border: { color: border },
                    ticks: { color: muted, maxTicksLimit: 8 }
                },
                y: {
                    grid: { color: border },
                    border: { color: border },
                    ticks: { color: muted, callback: v => fmtEUR(v) }
                }
            }
        }
    });
}

async function loadState() {
    try {
        const res = await fetch(STATE_URL, { cache: 'no-store' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return await res.json();
    } catch (err) {
        console.error('Failed to load state:', err);
        updateStatus(null, false);
        return null;
    }
}

async function refresh() {
    const state = await loadState();
    if (!state) return;
    updateStatus(state, true);
    updateStats(state);
    updatePositions(state);
    updateDecisions(state);
    updateTrades(state);
    updateChart(state);
}

refresh();
setInterval(refresh, 60000);
