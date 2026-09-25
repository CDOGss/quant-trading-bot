# Trading Bot – Paper Trading CAC40 📈

> **Simulation gratuite 100 %** – Aucun argent réel engagé.
> Capital simulé : **10 000 €** · Actifs : actions CAC40 & ETF · IA : **Gemini 3.8 Flash**

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  GitHub Actions (Cron : lun-ven 8h/10h/12h/14h UTC)                    │
│  ┌──────────────┐  ┌────────────────────────────┐  ┌──────────────┐   │
│  │  1. Fetch    │  │  2. Gemini 3.8 Flash      │  │  3. Update   │   │
│  │ Yahoo Finance│  │  (Thinking level: high)    │  │  State + Git  │   │
│  │  (yfinance)  │  │  Analyse + décision JSON   │  │  commit/push  │   │
│  └──────┬───────┘  └──────────────┬─────────────┘  └───────┬──────┘   │
└─────────┼──────────────────────────┼────────────────────────┼─────────┘
          ▼                          ▼                         ▼
   portfolio_state.json ←→ GitHub Pages → Tableau de bord statique (HTML/CSS/JS + Chart.js)
```

## 📁 Structure du dépôt

```
newtrade/
├── engine/
│   ├── trader.py           # Cerveau du bot (Python)
│   ├── requirements.txt
│   └── _test_gemini.py     # Test du chemin Gemini (mock)
├── dashboard/
│   ├── index.html          # Tableau de bord
│   ├── style.css
│   └── app.js
├── .github/
│   └── workflows/
│       ├── trading-bot.yml # Job trading (Cron + push)
│       └── pages.yml       # Déploiement GitHub Pages
├── portfolio_state.json    # Historique & state (commis par le bot)
└── README.md
```

## 🔧 Configuration

**Secret** (Settings → Secrets and variables → Actions → *Secrets*) :

| Secret | Description |
|--------|-------------|
| `GEMINI_API_KEY` | Clé API Gemini – https://aistudio.google.com/apikey. **Sans clé, le bot utilise des règles techniques** (RSI14 + MA20). |

**Variables optionnelles** (même page, onglet *Variables*) :

| Variable | Description |
|--------|-------------|
| `GEMINI_MODEL` | Modèle Gemini (défaut : `gemini-3.8-flash`) |
| `GEMINI_THINKING_LEVEL` | `low` / `medium` / `high` (défaut : `high`) |
| `MAX_POSITION_SIZE` | % de l'equity max par position (défaut : 25) |
| `MIN_TRADE_SIZE` | Montant min d'un trade en € (défaut : 100) |
| `INITIAL_CAPITAL` | Capital initial en € (défaut : 10000) |
| `ASK_BASKET` | Tickers Yahoo séparés par `;` (défaut : `CAC.PA;MC.PA;TTE.PA;AIR.PA;OR.PA;BNP.PA;SAN.PA;SU.PA`) |

## ▶️ Test local

```bash
cd engine
pip install -r requirements.txt
# Test du chemin Gemini + ordres (SDK mocké, sans clé)
python _test_gemini.py
# Règles techniques sur données réelles (sans clé Gemini)
SKIP_GEMINI=true python trader.py
# Hors-ligne (prix aléatoires)
SKIP_GEMINI=true MOCK_MARKET=true python trader.py
# Test réel (clé Gemini requise)
GEMINI_API_KEY=your_key python trader.py
```

## 🌐 Tableau de bord

Le dashboard est servi par GitHub Pages à :

```
https://cdogss.github.io/quant-trading-bot/
```

Il recharge automatiquement le `portfolio_state.json` toutes les 60 secondes.

## 📊 Données de marché

Le bot utilise [Yahoo Finance](https://www.yahoo.com/finance/) via `yfinance` (0 clé API).
Les symboles (suffixe `.PA` = Euronext Paris) :
- `CAC.PA` = Amundi CAC 40 UCITS ETF
- `MC.PA` = LVMH, `TTE.PA` = TotalEnergies, `AIR.PA` = Airbus, `OR.PA` = L'Oréal,
  `BNP.PA` = BNP Paribas, `SAN.PA` = Sanofi, `SU.PA` = Schneider Electric

## ⚖️ Gestion des risques

- Max **25 %** de l'equity par position
- Min **100 €** par trade
- Gemini (ou les règles) décide **ACHETER / VENDRE / CONSERVER** à chaque exécution (4×/jour en semaine)
- Historique : les 200 derniers trades + les 500 derniers snapshots d'equity

## 🚀 Déploiement

1. Settings → Pages → Source : **GitHub Actions**
2. (Optionnel) ajouter le secret `GEMINI_API_KEY`
3. Push sur `master` → `pages.yml` publie le dashboard
4. `trading-bot.yml` tourne au schedule (ou manuellement : Actions → Trading Bot → Run workflow),
   commite `portfolio_state.json`, puis `pages.yml` redéploie automatiquement (`workflow_run`)

## ⚠️ Avertissement

> Ce système est un **simulateur pédagogique**. Il ne constitue aucun conseil financier.
> Les décisions sont faites par une IA (Gemini) et peuvent être erronées.
> Aucun argent réel n'est engagé. Les données de marché peuvent être incorrectes.
