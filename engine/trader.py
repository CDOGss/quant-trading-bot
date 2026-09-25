# -*- coding: utf-8 -*-
"""
Trading Bot – Paper Trading CAC40 / Actions / ETF (simulation gratuite, 0 € réel).

Architecture :
  1. Récupération des cours (Yahoo Finance via yfinance, fallback API v8)
  2. Calcul des indicateurs (MA20, MA50, MA200, RSI14, RSI7)
  3. Décision : Gemini 3.8 Flash (thinking "high"), sinon règles techniques
  4. Exécution de l'ordre virtuel contre la cote (paper)
  5. Persistance : portfolio_state.json (commit/push fait par le workflow)

Env (secrets / variables GitHub) :
  GEMINI_API_KEY          – clé API Gemini (https://aistudio.google.com/apikey)
                            absente → décisions par règles techniques
  GEMINI_MODEL            – modèle Gemini (défaut: gemini-3.8-flash)
  GEMINI_THINKING_LEVEL   – thinking level: low | medium | high (défaut: high)
  MAX_POSITION_SIZE       – % de l'equity max par position (défaut: 25)
  MIN_TRADE_SIZE          – volume min en € pour éviter le bruit (défaut: 100)
  INITIAL_CAPITAL         – capital initial en € (défaut: 10000)
  ASK_BASKET              – symboles Yahoo séparés par ";" (défaut: voir DEFAULT_BASKET)
  SKIP_GEMINI=true        – force les règles techniques (pas d'appel Gemini)
  MOCK_MARKET=true        – prix aléatoires (test hors-ligne uniquement)
"""

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration par défaut (surpassable via env)
# ---------------------------------------------------------------------------

def env_float(name, default):
    return float(os.environ.get(name) or default)

def env_int(name, default):
    return int(os.environ.get(name) or default)

def env_str(name, default):
    return os.environ.get(name) or default

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "portfolio_state.json"

MAX_POSITION_SIZE = env_int("MAX_POSITION_SIZE", 25)          # % de l'equity
MIN_TRADE_SIZE    = env_float("MIN_TRADE_SIZE", 100.0)       # € min
INITIAL_CAPITAL   = env_float("INITIAL_CAPITAL", 10000.0)    # €
GEMINI_MODEL      = env_str("GEMINI_MODEL", "gemini-3.8-flash")
THINKING_LEVEL    = env_str("GEMINI_THINKING_LEVEL", "high")

# Symboles Yahoo Finance – les actions de Paris ont le suffixe ".PA"
DEFAULT_BASKET = [
    "CAC.PA",  # Amundi CAC 40 UCITS ETF
    "MC.PA",   # LVMH
    "TTE.PA",  # TotalEnergies
    "AIR.PA",  # Airbus
    "OR.PA",   # L'Oréal
    "BNP.PA",  # BNP Paribas
    "SAN.PA",  # Sanofi
    "SU.PA",   # Schneider Electric
]

def _dedupe(lst):
    seen = set()
    out = []
    for x in lst:
        if x.upper() not in seen:
            seen.add(x.upper())
            out.append(x)
    return out

BASKET = _dedupe([s.strip() for s in env_str("ASK_BASKET", ";".join(DEFAULT_BASKET)).split(";")
                  if s.strip()])

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

# ---------------------------------------------------------------------------
# Indicateurs techniques
# ---------------------------------------------------------------------------

def sma(prices, window=20):
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window

def rsi(prices, window=14):
    if len(prices) < window + 1:
        return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-window:]) / window
    avg_loss = sum(losses[-window:]) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def _pct(a, b):
    return round((a - b) / b * 100, 3) if b else None

def _round(v, n):
    return round(v, n) if v is not None else None

def indicators(prices):
    """Retourne un dict d'indicateurs calculés à partir d'une liste de prix."""
    if not prices or len(prices) < 22:
        return {}
    rets = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    return {
        "last":  prices[-1],
        "ret1d": _pct(prices[-1], prices[-2]),
        "ret1w": _pct(prices[-1], prices[-6]),
        "ret1m": _pct(prices[-1], prices[-22]),
        "ma20":  _round(sma(prices, 20), 3),
        "ma50":  _round(sma(prices, 50), 3),
        "ma200": _round(sma(prices, 200), 3),
        "rsi14": _round(rsi(prices, 14), 2),
        "rsi7":  _round(rsi(prices, 7), 2),
        # volatilité annualisée des rendements journaliers (%)
        "volatility": round(math.sqrt(var) * math.sqrt(252) * 100, 2),
    }

# ---------------------------------------------------------------------------
# Récupération des données de marché
# ---------------------------------------------------------------------------

def fetch_prices_from_yfinance(tickers, period="1y", interval="1d"):
    """Retourne { ticker: [prix chronologiques] } (liste vide si échec)."""
    try:
        import yfinance as yf
    except ImportError:
        print("[WARNING] yfinance not installed")
        return {t: [] for t in tickers}
    prices = {}
    for t in tickers:
        try:
            data = yf.Ticker(t).history(period=period, interval=interval)
            prices[t] = [] if data.empty else [round(float(v), 4) for v in data["Close"].dropna().values]
        except Exception as e:
            print(f"[WARNING] yfinance failed for {t}: {e}")
            prices[t] = []
    return prices

def fetch_prices_from_yahoo_v8(tickers):
    """Fallback : API Yahoo Finance v8 (JSON brut)."""
    import urllib.request
    prices = {}
    for t in tickers:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1y&interval=1d"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            close = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            prices[t] = [round(float(v), 4) for v in close if v is not None]
        except Exception as e:
            print(f"[WARNING] Yahoo v8 failed for {t}: {e}")
            prices[t] = []
    return prices

def get_market_data(tickers):
    """
    Essai 1: yfinance. Essai 2: API Yahoo v8 pour les tickers manquants.
    Les tickers sans données sont ignorés (jamais de prix inventés en prod).
    """
    if os.environ.get("MOCK_MARKET") == "true":
        import random
        print("[MARKET] MOCK_MARKET=true – random prices")
        mock = {}
        for t in tickers:
            p = [100.0]
            for _ in range(250):
                p.append(round(p[-1] * (1 + random.gauss(0.0003, 0.015)), 4))
            mock[t] = p
        return mock, "mock"

    print("[MARKET] Fetching via yfinance...")
    prices = fetch_prices_from_yfinance(tickers)
    source = "yfinance"
    missing = [t for t in tickers if not prices.get(t)]
    if missing:
        print(f"[MARKET] Missing via yfinance: {missing} – trying Yahoo v8...")
        v8 = fetch_prices_from_yahoo_v8(missing)
        for t in missing:
            prices[t] = v8.get(t, [])
        source = "yfinance+yahoo_v8" if len(missing) < len(tickers) else "yahoo_v8"
    prices = {t: p for t, p in prices.items() if p}
    print("[MARKET] OK: " + ", ".join(f"{t}({len(p)})" for t, p in prices.items()))
    return prices, source

# ---------------------------------------------------------------------------
# Décisions – Gemini ou règles techniques
# ---------------------------------------------------------------------------

def build_system_prompt():
    return f"""
You are a professional quant trading bot specializing in CAC40 large caps and French
equity ETFs. You run a PAPER portfolio and produce ONE decision per ticker per snapshot.

Rules:
1. Return ONLY valid JSON, no markdown, no text outside the JSON.
2. Decide ONE of three actions per ticker:
   - "BUY"   : open a position (max {MAX_POSITION_SIZE}% of equity)
   - "SELL"  : close the existing position
   - "HOLD"  : no action (keep position or stay flat)
3. Base your decision on the provided indicators (RSI, MAs, returns, volatility)
   and on the current positions (you cannot SELL what you don't hold, and a BUY on a
   ticker already held is ignored).
4. Strong uptrend (RSI > 55, price > MA20, positive ret1d) → you MAY buy.
5. Strong downtrend (RSI < 45, price < MA20, negative ret1d) → you SHOULD sell if holding.
6. Range (RSI 45-55, near MAs) → you SHOULD hold.
7. Never exceed {MAX_POSITION_SIZE}% of equity in any single ticker.

JSON output format:
{{
  "decisions": [
    {{
      "ticker": "MC.PA",
      "action": "BUY|SELL|HOLD",
      "confidence": 0.0-1.0,
      "reason": "one-sentence justification in English",
      "max_position_pct": <= {MAX_POSITION_SIZE}
    }}
  ],
  "portfolio_strategy": "string summarizing overall stance",
  "risk_check": "string summarizing risk management"
}}
"""

def build_user_prompt(markets, holdings, equity, cash):
    lines = [
        "CURRENT PORTFOLIO STATE:",
        f"  Equity: €{equity:.2f}",
        f"  Cash:   €{cash:.2f}",
        f"  Initial Capital: €{INITIAL_CAPITAL:.2f}",
        f"  ROI:    {(equity / INITIAL_CAPITAL - 1) * 100:.2f}%",
        "",
        "OPEN POSITIONS:",
    ]
    if not holdings:
        lines.append("  (none)")
    for sym, pos in holdings.items():
        lines.append(f"  {sym}: {pos['shares']:.3f} shares at €{pos['avg_price']:.2f}/share "
                     f"(P&L {pos['pnl']:.2f}€)")
    lines += ["", "MARKET DATA (daily closes, last 1y):"]
    for sym, prices in markets.items():
        inds = indicators(prices)
        if inds:
            lines.append(f"  {sym}: " + " ".join(f"{k}={v}" for k, v in inds.items()))
    lines += ["", "TASK: Decide BUY/SELL/HOLD for each ticker. Return JSON only."]
    return "\n".join(lines)

def parse_json_response(text):
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini returned invalid JSON: {e}\nRAW: {text[:500]}")

def ask_gemini(system_prompt, user_prompt, model=GEMINI_MODEL, thinking_level=THINKING_LEVEL):
    """Appelle Gemini via le SDK google-genai et retourne le JSON parsé."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
        ),
    )
    return parse_json_response(resp.text or "")

def rule_based_decisions(markets, holdings):
    """Stratégie de secours : mêmes règles que le prompt Gemini, déterministe."""
    decisions = []
    for sym, prices in markets.items():
        inds = indicators(prices)
        if not inds or inds["rsi14"] is None or inds["ma20"] is None:
            continue
        r, last, ma20, d1 = inds["rsi14"], inds["last"], inds["ma20"], inds["ret1d"]
        if r > 55 and last > ma20 and d1 > 0 and sym not in holdings:
            action, reason = "BUY", f"Uptrend: RSI14 {r} > 55, price above MA20, +{d1}% today"
            conf = min(0.9, 0.5 + (r - 55) / 50)
        elif r < 45 and last < ma20 and d1 < 0 and sym in holdings:
            action, reason = "SELL", f"Downtrend: RSI14 {r} < 45, price below MA20, {d1}% today"
            conf = min(0.9, 0.5 + (45 - r) / 50)
        else:
            action, reason, conf = "HOLD", f"No clear signal (RSI14 {r})", 0.5
        decisions.append({"ticker": sym, "action": action, "confidence": round(conf, 2),
                          "reason": reason, "max_position_pct": MAX_POSITION_SIZE})
    return {"decisions": decisions,
            "portfolio_strategy": "Rule-based trend following (RSI14 + MA20)",
            "risk_check": f"Max {MAX_POSITION_SIZE}% of equity per position"}

def get_decisions(markets, state):
    if os.environ.get("SKIP_GEMINI") == "true":
        print("[DECISION] SKIP_GEMINI=true → rule-based")
        return rule_based_decisions(markets, state["holdings"]), "rules"
    if not os.environ.get("GEMINI_API_KEY"):
        print("[DECISION] GEMINI_API_KEY absent → rule-based")
        return rule_based_decisions(markets, state["holdings"]), "rules"
    try:
        d = ask_gemini(build_system_prompt(),
                       build_user_prompt(markets, state["holdings"], state["equity"], state["cash"]))
        print(f"[DECISION] Gemini ({GEMINI_MODEL}): {d.get('portfolio_strategy', 'N/A')}")
        return d, GEMINI_MODEL
    except Exception as e:
        print(f"[DECISION] Gemini failed ({e}) → rule-based")
        return rule_based_decisions(markets, state["holdings"]), "rules (gemini error)"

# ---------------------------------------------------------------------------
# Exécution des trades (paper)
# ---------------------------------------------------------------------------

def mark_to_market(state, last_prices):
    """Met à jour la valeur de marché / P&L de chaque position et l'equity."""
    for sym, pos in state["holdings"].items():
        price = last_prices.get(sym)
        if price:
            pos["last_price"] = price
            pos["market_value"] = round(pos["shares"] * price, 2)
            pos["pnl"] = round((price - pos["avg_price"]) * pos["shares"], 2)
    state["equity"] = round(state["cash"] + sum(p["market_value"] for p in state["holdings"].values()), 2)

def execute_orders(state, decisions, last_prices):
    """Exécute les décisions sur le state (paper). Retourne la liste des trades."""
    trades = []
    equity = state["equity"]
    for d in decisions.get("decisions", []):
        sym = d.get("ticker")
        action = str(d.get("action", "HOLD")).upper()
        price = last_prices.get(sym)
        if not price:
            print(f"[ORDER] SKIP {sym} (no price)")
            continue
        pos = state["holdings"].get(sym)

        if action == "BUY":
            if pos:
                print(f"[ORDER] SKIP BUY {sym} (already holding)")
                continue
            try:
                pct = min(float(d.get("max_position_pct") or MAX_POSITION_SIZE), MAX_POSITION_SIZE)
            except (TypeError, ValueError):
                pct = MAX_POSITION_SIZE
            budget = min(equity * pct / 100.0, state["cash"])
            shares = math.floor(budget / price * 1000) / 1000   # 3 décimales, arrondi bas
            cost = round(shares * price, 2)
            if cost < MIN_TRADE_SIZE:
                print(f"[ORDER] SKIP BUY {sym}: order too small (€{cost:.2f})")
                continue
            state["cash"] = round(state["cash"] - cost, 2)
            state["holdings"][sym] = {
                "shares": shares, "avg_price": price, "last_price": price,
                "market_value": cost, "pnl": 0.0, "opened": now_iso(),
            }
            trades.append({"timestamp": now_iso(), "ticker": sym, "action": "BUY",
                           "shares": shares, "price": price, "amount": cost,
                           "confidence": d.get("confidence", 0.5), "reason": d.get("reason", "")})
            print(f"[ORDER] BUY {sym} {shares} @ €{price:.2f} (€{cost:.2f})")

        elif action == "SELL":
            if not pos:
                print(f"[ORDER] SKIP SELL {sym} (no position)")
                continue
            proceeds = round(pos["shares"] * price, 2)
            pnl = round((price - pos["avg_price"]) * pos["shares"], 2)
            state["cash"] = round(state["cash"] + proceeds, 2)
            del state["holdings"][sym]
            trades.append({"timestamp": now_iso(), "ticker": sym, "action": "SELL",
                           "shares": pos["shares"], "price": price, "amount": proceeds, "pnl": pnl,
                           "confidence": d.get("confidence", 0.5), "reason": d.get("reason", "")})
            print(f"[ORDER] SELL {sym} {pos['shares']} @ €{price:.2f} (+€{proceeds:.2f}, P&L {pnl:+.2f})")
    return trades

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_state(path=STATE_PATH):
    if path.exists():
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {
        "initial_capital": INITIAL_CAPITAL,
        "cash": INITIAL_CAPITAL,
        "holdings": {},
        "equity": INITIAL_CAPITAL,
        "trades": [],
        "history": [],
        "updated": now_iso(),
    }

def save_state(state, path=STATE_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")

def main():
    # Console Windows (cp1252) : évite les UnicodeEncodeError sur € / →
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    state = load_state()

    # 1. Market data
    prices, source = get_market_data(BASKET)
    if not prices:
        print("[ERROR] No market data for any ticker – state left untouched.")
        sys.exit(1)
    last_prices = {sym: p[-1] for sym, p in prices.items()}
    mark_to_market(state, last_prices)

    # 2. Decisions
    decisions, engine = get_decisions(prices, state)

    # 3. Orders
    new_trades = execute_orders(state, decisions, last_prices)
    mark_to_market(state, last_prices)

    # 4. State
    ts = now_iso()
    state["updated"] = ts
    state["market_source"] = source
    state["decision_engine"] = engine
    state["last_decisions"] = {
        "timestamp": ts,
        "strategy": decisions.get("portfolio_strategy", ""),
        "risk_check": decisions.get("risk_check", ""),
        "decisions": decisions.get("decisions", []),
    }
    state["prices"] = {sym: {"last": inds["last"], "ret1d": inds["ret1d"], "rsi14": inds["rsi14"]}
                       for sym, inds in ((s, indicators(p)) for s, p in prices.items()) if inds}
    state["history"] = (state.get("history", []) + [
        {"timestamp": ts, "equity": state["equity"], "cash": state["cash"]}
    ])[-500:]
    state["trades"] = (state.get("trades", []) + new_trades)[-200:]

    # 5. Save
    save_state(state)
    print(f"[DONE] Equity: €{state['equity']:.2f} "
          f"(ROI {(state['equity'] / state['initial_capital'] - 1) * 100:.2f}%)")
    print(f"[DONE] Cash: €{state['cash']:.2f} · Positions: {len(state['holdings'])} "
          f"· New trades: {len(new_trades)} · Engine: {engine}")
    return state

if __name__ == "__main__":
    main()
