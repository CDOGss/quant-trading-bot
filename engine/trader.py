# -*- coding: utf-8 -*-
"""
Trading Bot – Paper Trading CAC40 / Actions / ETF (simulation gratuite, 0 € réel).

Architecture :
  1. Récupération des cours (Yahoo Finance via yfinance, fallback API v8)
  2. Calcul des indicateurs (MA20, MA50, RSI14, SMA7)
  3. Prompt Gemini 3.8 Flash (mode Thinking "high") – décision JSON
  4. Exécution de l'ordre virtuel contre la cote (paper)
  5. Persistance : portfolio_state.json + commit/push (fait par le workflow)

Env requis (secrets GitHub) :
  GEMINI_API_KEY          – clé API Gemini (https://aistudio.google.com/apikey)
  GEMINI_MODEL            – modèle Gemini (défaut: gemini-3.8-flash)
  GEMINI_THINKING_LEVEL   – thinking level: low | medium | high (défaut: high)
  MAX_POSITION_SIZE       – % du capital max par position (défaut: 25)
  MIN_TRADE_SIZE          – volume min en € pour éviter le bruit (défaut: 100)
  INITIAL_CAPITAL         – capital initial en € (défaut: 10000)
  ASK_BASKET              – liste de symboles à surveiller (défaut: 6C40)
"""

import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Configuration par défaut (surpassable via env)
# ---------------------------------------------------------------------------

def env_float(name, default):
    return float(os.environ.get(name, str(default)))

def env_int(name, default):
    return int(os.environ.get(name, str(default)))

def env_str(name, default):
    return os.environ.get(name, default)

MAX_POSITION_SIZE = env_int("MAX_POSITION_SIZE", 25)          # % du capital
MIN_TRADE_SIZE     = env_float("MIN_TRADE_SIZE", 100.0)      # € min
INITIAL_CAPITAL    = env_float("INITIAL_CAPITAL", 10000.0)   # €
ASK_BASKET       = [s.strip() for s in env_str("ASK_BASKET",
          "6C40;EDV.P;AX.P;ED.P;EN.P;AMX.P;AC.P").split(";")
          if s.strip()]

# Symboles Yahoo pour CAC40 et actions françaises
# 6C40  = indice CAC40
# Les actions françaises utilisent la suffixe ".P" sur Yahoo
DEFAULT_BASKET = [
    "6C40",   # CAC40 indice
    "EDV.P",  # iShares Core CAC 40 ETF
    "AX.P",   # LVMH
    "ED.P",   # EDF
    "EN.P",   # TotalEnergies
    "AMX.P",  # Airbus
    "AC.P",   # Lacroix
]

# Dedupe et on garde un basket réaliste
def _dedupe(lst):
    seen = set()
    out = []
    for x in lst:
        if x.upper() not in seen:
            seen.add(x.upper())
            out.append(x)
    return out

BASKET = _dedupe(ASK_BASKET + DEFAULT_BASKET)

# ---------------------------------------------------------------------------
# Indicateurs techniques
# ---------------------------------------------------------------------------

def sma(prices, window=20):
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window

def ema(prices, window=12):
    if len(prices) < 2:
        return None
    alpha = 2 / (window + 1)
    out = [prices[0]]
    for p in prices[1:]:
        out.append(alpha * p + (1 - alpha) * out[-1])
    return out

def rsi(prices, window=14):
    if len(prices) < window + 1:
        return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-window:]) / window
    avg_loss  = sum(losses[-window:]) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def indicators(prices):
    """Retourne un dict d'indicateurs calculés à partir d'une liste de prix."""
    if not prices or len(prices) < 20:
        return {}
    ret = {}
    ret["last"]       = prices[-1]
    ret["prev"]       = prices[-2]
    ret["ret1d"]      = round((prices[-1] - prices[-2]) / prices[-2] * 100, 3)
    ret["ret1w"]      = round((prices[-1] - prices[-8]) / prices[-8] * 100, 3)
    ret["ret1m"]      = round((prices[-1] - prices[-22]) / prices[-22] * 100, 3)
    ret["ma20"]       = round(sma(prices, 20), 3)
    ret["ma50"]       = round(sma(prices, 50), 3)
    ret["ma200"]      = round(sma(prices, 200), 3)
    ret["rsi14"]      = round(rsi(prices, 14), 2)
    ret["rsi7"]       = round(rsi(prices, 7), 2)
    ret["volatility"] = round(math.sqrt(sum((prices[i]-prices[i-1])**2 for i in range(1,len(prices)))/max(1,len(prices)-1)), 4)
    return ret

# ---------------------------------------------------------------------------
# Récupération des données de marché
# ---------------------------------------------------------------------------

def fetch_prices_from_yfinance(tickers, period="1y", interval="1d"):
    """
    Récupère les prix depuis yfinance.
    Retourne un dict { ticker: [prix_1, prix_2, ...] } (ordré croissant dans le temps).
    """
    import yfinance as yf
    prices = {}
    for t in tickers:
        try:
            data = yf.Ticker(t).history(period=period, interval=interval)
            if data.empty:
                prices[t] = []
            else:
                prices[t] = [round(float(v), 4) for v in data["Close"].values]
        except Exception as e:
            print(f"[WARNING] yfinance failed for {t}: {e}")
            prices[t] = []
    return prices

def fetch_prices_from_yahoo_v8(tickers):
    """
    Fallback: utilise l'API Yahoo Finance v8 (plus stable sur GitHub Actions).
    Retourne { ticker: [prix_1, ..., prix_n] } (chronologique).
    """
    import urllib.request
    import time
    urls = []
    for t in tickers:
        period1 = int(time.time() - 365 * 86400)
        period2 = int(time.time())
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
            f"?period1={period1}&period2={period2}&interval=1d"
            f"&events=history&range=1y"
        )
        urls.append((t, url))

    prices = {}
    for t, url in urls:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                }
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            close = [float(v) for v in data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
                     if v is not None]
            prices[t] = close
        except Exception as e:
            print(f"[WARNING] Yahoo v8 failed for {t}: {e}")
            prices[t] = []
    return prices

def get_market_data(tickers):
    """
    Essai 1: yfinance (plus complet).
    Essai 2: API Yahoo v8.
    """
    print("[MARKET] Fetching via yfinance...")
    prices = fetch_prices_from_yfinance(tickers)
    if all(len(prices[t]) > 0 for t in tickers):
        ok = [f"{t}({len(prices[t])})" for t in tickers]
        print("[MARKET] yfinance OK: " + ", ".join(ok))
        return prices, "yfinance"
    print("[MARKET] yfinance insufficient – trying Yahoo v8...")
    prices_v8 = fetch_prices_from_yahoo_v8(tickers)
    if all(len(prices_v8[t]) > 0 for t in tickers):
        print("[MARKET] Yahoo v8 OK")
        return prices_v8, "yahoo_v8"
    # Fallback : si on n'a rien, on retourne des prix mock (pour le test local)
    import random
    prices_mock = {t: [100 + random.gauss(0, 5) for _ in range(60)] for t in tickers}
    print("[MARKET] FALLBACK: mock prices generated")
    return prices_mock, "mock"

# ---------------------------------------------------------------------------
# Gemini – le cerveau du bot
# ---------------------------------------------------------------------------

def build_system_prompt():
    return """
You are a professional quant trading bot specializing in intraday CAC40 and French
large-cap ETFs. Your job is to produce ONE trading decision per market data snapshot.

Rules:
1. You MUST return ONLY valid JSON, no markdown, no text outside the JSON.
2. Decide ONE of three actions per ticker:
   - "BUY"   : open a position (max MAX_POSITION_SIZE% of equity)
   - "SELL"  : close existing position
   - "HOLD"  : no action (keep position or stay flat)
3. Your decision MUST be based on the provided indicators (RSI, MAs, returns).
4. If the ticker is in strong trend (RSI > 55, price > MA20, positive ret1d),
   you MAY buy up to MAX_POSITION_SIZE% of portfolio.
5. If the ticker is in strong downtrend (RSI < 45, price < MA20, negative ret1d),
   you SHOULD sell if holding.
6. If the ticker is in range (RSI 45-55, near MAs), you SHOULD hold.
7. You cannot over-leverage: never exceed MAX_POSITION_SIZE% in any single ticker.
8. Total deployed capital + cash = portfolio equity.

JSON output format:
{
  "decisions": [
    {
      "ticker": "6C40",
      "action": "BUY|SELL|HOLD",
      "confidence": 0.0-1.0,
      "reason": "one-sentence justification in English",
      "max_position_pct": <= MAX_POSITION_SIZE
    }
  ],
  "portfolio_strategy": "string summarizing overall stance",
  "risk_check": "string summarizing risk management"
}

Do not use French. Do not add extra fields.
"""

def build_user_prompt(markets, holdings, equity, cash, model, thinking_level):
    lines = []
    lines.append("CURRENT PORTFOLIO STATE:")
    lines.append(f"  Equity: €{equity:.2f}")
    lines.append(f"  Cash:  €{cash:.2f}")
    lines.append(f"  Initial Capital: €{INITIAL_CAPITAL:.2f}")
    lines.append(f"  ROI:   {(equity/INITIAL_CAPITAL - 1) * 100:.2f}%")
    lines.append("")
    lines.append("OPEN POSITIONS:")
    for sym, pos in holdings.items():
        lines.append(f"  {sym}: {pos['shares']:.3f} shares at €{pos['avg_price']:.2f}/share (P&L {pos['pnl']:.2f}€)")
    lines.append("")
    lines.append("MARKET DATA:")
    for sym in markets:
        prices = markets[sym]
        if not isinstance(prices, list) or len(prices) == 0:
            continue
        inds = indicators(prices)
        if inds:
            lines.append(f"  {sym}: last={inds['last']:.2f} ret1d={inds['ret1d']:.2f}% "
                         f"RSI14={inds['rsi14']} RSI7={inds['rsi7']} MA20={inds['ma20']:.2f} "
                         f"MA50={inds['ma50']:.2f} ret1w={inds['ret1w']:.2f}%")
    lines.append("")
    lines.append("TASK: Decide BUY/SELL/HOLD for each ticker. Return JSON only.")
    lines.append(f"MODEL: {model}")
    lines.append(f"THINKING_LEVEL: {thinking_level}")
    return "\n".join(lines)

def ask_gemini(system_prompt, user_prompt, model=None, thinking_level="high"):
    """
    Appelle l'API Gemini via Google GenAI SDK.
    Retourne le JSON parseé de la réponse du modèle.
    """
    try:
        from google import generative_ai
        from google.generative_ai import client
    except ImportError as e:
        raise RuntimeError(f"google-generative-ai not installed. Run: pip install google-generative-ai ({e})")

    gemini_client = client.GenerativeAIClient(api_key=os.environ["GEMINI_API_KEY"])
    resp = gemini_client.generate_text(
        prompt=user_prompt,
        model=model or env_str("GEMINI_MODEL", "gemini-3.8-flash"),
        temperature=0.1,
        top_p=0.9,
        max_output_tokens=500,
    )
    # Le SDK peut retourner un objet avec .text ou directement une str
    response = getattr(resp, "text", resp)
    if isinstance(response, bytes):
        response = response.decode("utf-8")
    cleaned = response
    if "```" in cleaned:
        # Extraire la partie entre les ``` json ```
        import re
        m = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1)
    # Parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini returned invalid JSON: {e}\nRAW: {response[:500]}")

# ---------------------------------------------------------------------------
# Exécution des trades (paper)
# ---------------------------------------------------------------------------

def execute_orders(state, decisions, last_prices):
    """
    Exécute les décisions Gemini et met à jour le state.
    `last_prices` = { sym: dernier_prix_float }.
    """
    cash = state["cash"]
    holdings = state["holdings"]
    trades = []
    lp = last_prices

    for d in decisions.get("decisions", []):
        sym = d.get("ticker")
        action = d.get("action", "HOLD").upper()
        if sym not in last_prices:
            print(f"[ORDER] SKIP {sym} (no data)")
            continue
        price = lp.get(sym)
        if not price:
            print(f"[ORDER] SKIP {sym} (no price)")
            continue

        existing = holdings.get(sym, None)
        existing_shares = existing["shares"] if existing else 0.0

        if action == "BUY":
            # Max position size = % of equity
            max_shares = (cash * d.get("max_position_pct", MAX_POSITION_SIZE) / 100.0) / price
            if existing_shares > 0:
                continue  # already holding
            if max_shares * price < MIN_TRADE_SIZE:
                print(f"[ORDER] SKIP BUY {sym}: order too small")
                continue
            shares_to_buy = max_shares
            cost = shares_to_buy * price
            # Round to 3 decimals (standard stock fraction)
            shares_to_buy = round(shares_to_buy, 3)
            cost = shares_to_buy * price
            if cost > cash:
                shares_to_buy = cash / price
                cost = shares_to_buy * price
                shares_to_buy = round(shares_to_buy, 3)
            if cost < MIN_TRADE_SIZE:
                print(f"[ORDER] SKIP BUY {sym}: order too small after rounding")
                continue
            cash -= cost
            avg_price = price  # new position
            holdings[sym] = {
                "shares": shares_to_buy,
                "avg_price": avg_price,
                "market_value": cost,
                "pnl": 0.0,
                "action": "buy"
            }
            trades.append({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "ticker": sym,
                "action": action,
                "shares": shares_to_buy,
                "price": price,
                "cost": cost,
                "confidence": d.get("confidence", 0.5),
                "reason": d.get("reason", "")
            })
            print(f"[ORDER] BUY {sym} {shares_to_buy} @ €{price:.2f} (€{cost:.2f})")

        elif action == "SELL":
            if existing is None:
                print(f"[ORDER] SKIP SELL {sym} (no position)")
                continue
            shares_to_sell = existing["shares"]
            proceeds = shares_to_sell * price
            cash += proceeds
            del holdings[sym]
            trades.append({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "ticker": sym,
                "action": action,
                "shares": shares_to_sell,
                "price": price,
                "proceeds": proceeds,
                "confidence": d.get("confidence", 0.5),
                "reason": d.get("reason", "")
            })
            print(f"[ORDER] SELL {sym} {shares_to_sell} @ €{price:.2f} (+€{proceeds:.2f})")

        else:
            # HOLD : update P&L (marché mis à jour)
            existing_shares_val = existing["shares"] if existing else 0.0
            existing_pnl_val = existing["pnl"] if existing else 0.0
            if existing:
                existing["market_value"] = existing["shares"] * price
                existing["pnl"] = (price - existing["avg_price"]) * existing["shares"]
            trades.append({
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "ticker": sym,
                "action": "HOLD",
                "shares": existing_shares_val,
                "price": price,
                "pnl": existing_pnl_val,
                "confidence": d.get("confidence", 0.5),
                "reason": d.get("reason", "")
            })
    return cash, holdings, trades

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_state(path="portfolio_state.json"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Seed initial state
    return {
        "initial_capital": INITIAL_CAPITAL,
        "cash": INITIAL_CAPITAL,
        "holdings": {},
        "equity": INITIAL_CAPITAL,
        "trades": [],
        "history": [],
        "updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }

def save_state(state, path="portfolio_state.json"):
    state["updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def main():
    state = load_state()

    # 1. Fetch market data (prices is already {sym: [prix chronologique]} ou {sym: dernier_prix} en fallback)
    prices, source = get_market_data(BASKET)
    print(f"[MARKET] Source: {source}, tickers: {len(prices)}")

    # Normalise last_prices : si le fallback a déjà renvoyé un float, on le garde
    last_prices = {}
    for sym, val in prices.items():
        if isinstance(val, list) and val:
            last_prices[sym] = val[-1]
        elif isinstance(val, (int, float)):
            last_prices[sym] = float(val)

    # 2. Get Gemini decision
    if os.environ.get("SKIP_GEMINI") == "true":
        # Mock decisions for testing
        import random
        decisions = {
            "decisions": [
                {
                    "ticker": sym,
                    "action": random.choice(["BUY", "SELL", "HOLD"]),
                    "confidence": round(random.random() * 0.9 + 0.1, 3),
                    "reason": "mock decision for testing",
                    "max_position_pct": MAX_POSITION_SIZE
                } for sym in last_prices
            ],
            "portfolio_strategy": "balanced",
            "risk_check": "ok"
        }
        print("[DECISION] Using mock Gemini (SKIP_GEMINI=true)")
    else:
        decisions = ask_gemini(build_system_prompt(), build_user_prompt(
            last_prices, state["holdings"], state["equity"], state["cash"],
            env_str("GEMINI_MODEL", "gemini-3.8-flash"), env_str("GEMINI_THINKING_LEVEL", "high")
        ))
        print("[DECISION] Gemini decision received: " + str(decisions.get("portfolio_strategy", "N/A")))
        print("[DECISION] Gemini decision received")

    # 3. Execute orders
    new_cash, new_holdings, new_trades = execute_orders(state, decisions, last_prices)

    # 4. Update state
    state["cash"] = new_cash
    state["holdings"] = new_holdings
    state["equity"] = new_cash + sum(h["market_value"] for h in new_holdings.values())
    state["history"].append({
        "timestamp": state["updated"],
        "equity": state["equity"],
        "cash": state["cash"]
    })
    # Keep history to 100 entries
    state["history"] = state["history"][-100:]
    state["trades"] = (state["trades"] + new_trades)[-200:]

    # 5. Save
    save_state(state)
    print(f"[DONE] Equity: €{state['equity']:.2f} (ROI {(state['equity']/state['initial_capital']-1)*100:.2f}%)")
    print(f"[DONE] Cash: €{state['cash']:.2f}")
    print(f"[DONE] Trades: {len(state['trades'])}")

    return state

if __name__ == "__main__":
    main()
