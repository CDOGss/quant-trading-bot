# Trading Bot – Paper Trading CAC40 📈

> **Simulation gratuite 100 %** – Aucun argent réel engagé.
> Capital simulé : **10 000 €** · Actifs : actions CAC40 & ETF · IA : **Gemini 3.8 Flash**

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  GitHub Actions (Cron : lun-ven 8h/10h/14h/16h CET)                   │
│  ┌──────────────┐  ┌────────────────────────────┐  ┌──────────────┐   │
│  │  1. Fetch    │  │  2. Gemini 3.8 Flash      │  │  3. Update   │   │
│  │  Yahoo Finance│ │  (Thinking level: high)    │  │  State + Git  │   │
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

## 🔧 Configuration (GitHub Secrets)

| Secret | Description |
|--------|-------------|
| `GEMINI_API_KEY` | Clé API Gemini – https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | Modél Gemini (défaut: `gemini-3.8-flash`) |
| `GEMINI_THINKING_LEVEL` | `low` / `medium` / `high` (défaut: `high`) |
| `MAX_POSITION_SIZE` | % du capital max par position (défaut: 25) |
| `MIN_TRADE_SIZE` | Montant min d'un trade en € (défaut: 100) |
| `INITIAL_CAPITAL` | Capital initial en € (défaut: 10000) |
| `ASK_BASKET` | Liste de tickers séparer par `;` (défaut: `6C40;EDV.P;AX.P;ED.P;EN.P;AMX.P;AC.P`) |

## ▶️ Test local

```bash
cd engine
pip install -r requirements.txt
# Test en mode mock (sans clé Gemini, sans internet)
SKIP_GEMINI=true python trader.py
# Test réel (clé Gemini requise)
GEMINI_API_KEY=your_key python trader.py
```

## 🌐 Tableau de bord

Le dashboard est servi par GitHub Pages à :

```
https://<votre-username>.github.io/<repo-name>/
```

Il recharge automatiquement le `portfolio_state.json` toutes les 60 secondes.

## 📊 Données de marché

Le bot utilise [Yahoo Finance](https://www.yahoo.com/finance/) via `yfinance` (0 clé API).
Les symboles :
- `6C40` = indice CAC40
- `EDV.P` = iShares Core CAC 40 ETF
- `AX.P` = LVMH, `ED.P` = EDF, `EN.P` = TotalEnergies, `AMX.P` = Airbus, `AC.P` = Lacroix

## ⚖️ Gestion des risques

- Max **25 %** du capital par position
- Min **100 €** par trade
- Gemini décide **ACHETER / VENDRE / CONSERVER** à chaque tick (2h)
- Historique : les 200 derniers trades + les 100 derniers snapshots

## 🚀 Déploiement

1. Forker/cloner ce dépôt
2. Sur GitHub : Settings → Pages → Branch → `main`
3. Ajouter les secrets dans Settings → Secrets
4. Push → le workflow `trading-bot.yml` s'exécute automatiquement à chaque push + au schedule
5. Le `portfolio_state.json` est commité/pushed par le job
6. Le dashboard est redéployé via `pages.yml`

## ⚠️ Avertissement

> Ce système est un **simulateur pédagogique**. Il ne constitue aucun conseil financier.
> Les décisions sont faites par une IA (Gemini) et peuvent être erronées.
> Aucun argent réel n'est engagé. Les données de marché peuvent être incorrectes.
