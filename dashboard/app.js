// ============================================================
// Trading Bot Dashboard – Paper Trading CAC40
// Fetch portfolio_state.json depuis GitHub Pages et affiche
// le tableau de bord en temps quasi-réel.
// ============================================================

// In GitHub Pages: on utilise la relative path (le dépât est racine)
const STATE_URL = 'portfolio_state.json';
let chart = null;

function fmtEUR(v) {
    return v.toFixed(2) + ' €';
}

function updateStatus(state, ok) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const ts = document.getElementById('timestamp');

    if (ok && state) {
        dot.className = 'dot';
        text.textContent = 'En ligne';
        const updated = new Date(state.updated).toLocaleTimeString('fr-FR', {
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
        ts.textContent = `MàJ ${updated}`;
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
        (state.trades || []).length;
    const roi = state.equity / state.initial_capital - 1;
    const roiEl = document.getElementById('roi');
    roiEl.textContent = (roi * 100).toFixed(2) + '%';
    roiEl.style.color = roi >= 0 ? 'var(--accent)' : 'var(--red)';
}

function updatePositions(state) {
    const tbody = document.querySelector('#positions-table tbody');
    const holdings = state.holdings || {};
    if (Object.keys(holdings).length === 0) {
        tbody.innerHTML =
            '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">Aucune position ouverte</td></tr>';
        return;
    }
    tbody.innerHTML = Object.entries(holdings).map(([sym, pos]) => {
        const pnlClass = pos.pnl >= 0 ? 'pos-pnl-positive' : 'pos-pnl-negative';
        return `
            <tr>
                <td>${sym}</td>
                <td>${pos.shares.toFixed(3)}</td>
                <td>${fmtEUR(pos.avg_price)}</td>
                <td>${fmtEUR(pos.market_value)}</td>
                <td class="${pnlClass}">${pos.pnl >= 0 ? '+' : ''}${fmtEUR(pos.pnl)}</td>
            </tr>`;
    }).join('');
}

function updateTrades(state) {
    const tbody = document.querySelector('#trades-table tbody');
    const trades = state.trades || [];
    if (trades.length === 0) {
        tbody.innerHTML =
            '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);">Aucun trade enregistré</td></tr>';
        return;
    }
    tbody.innerHTML = trades
        .slice(0, 50)
        .reverse()
        .map((t) => {
            const ts = new Date(t.timestamp).toLocaleString('fr-FR', {
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit'
            });
            const conf = t.confidence || 0;
            const confClass =
                t.action === 'BUY' ? 'action-buy' :
                t.action === 'SELL' ? 'action-sell' : 'action-hold';
            return `
                <tr>
                    <td>${ts}</td>
                    <td>${t.ticker}</td>
                    <td class="${confClass}">${t.action}</td>
                    <td>${t.shares?.toFixed(3) || 0}</td>
                    <td>${fmtEUR(t.price)}</td>
                    <td>
                        <div class="conf-bar">
                            <div class="bar"><div class="bar-fill" style="width:${conf * 100}%"></div></div>
                            <span>${Math.round(conf * 100)}%</span>
                        </div>
                    </td>
                    <td>${t.reason || ''}</td>
                </tr>`;
        }).join('');
}

function initChart(data) {
    const canvas = document.getElementById('capitalChart');
    const history = stateToHistory(data.history || [], data.equity);

    if (chart) chart.destroy();

    chart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: history.map(h => new Date(h.timestamp).toLocaleDateString('fr-FR')),
            datasets: [{
                label: 'Capital',
                data: history.map(h => h.equity),
                borderColor: 'var(--accent)',
                backgroundColor: gradient('var(--accent)'),
                tension: 0.3,
                fill: true,
                borderWidth: 2,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => 'Capital: ' + fmtEUR(ctx.parsed.y)
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'var(--border)' },
                    border: { color: 'var(--border)' }
                },
                y: {
                    grid: { color: 'var(--border)' },
                    border: { color: 'var(--border)' },
                    ticks: {
                        callback: v => fmtEUR(v)
                    }
                }
            }
        }
    });
}

function gradient(colorVar) {
    return '#10b98122';
}

function stateToHistory(history, currentEquity) {
    if (!history || history.length === 0) return [];
    return history.map(h => ({
        timestamp: h.timestamp,
        equity: h.equity
    }));
}

async function loadState() {
    try {
        // GitHub Pages sert le dashboard depuis la racine du dépôt,
        // donc 'portfolio_state.json' est directement accessible
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
    if (state) {
        updateStatus(state, true);
        updateStats(state);
        updatePositions(state);
        updateTrades(state);
        initChart(state);
    }
}

// Initial load
refresh();

// Refresh every 60 seconds
setInterval(refresh, 60000);
