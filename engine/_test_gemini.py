# -*- coding: utf-8 -*-
"""Test le chemin Gemini (SDK google-genai mocké) et l'exécution des ordres, sans clé réelle."""
import sys
import types
import json
import os

google_pkg = types.ModuleType('google')
genai_mod  = types.ModuleType('google.genai')
types_mod  = types.ModuleType('google.genai.types')
sys.modules['google'] = google_pkg
sys.modules['google.genai'] = genai_mod
sys.modules['google.genai.types'] = types_mod
google_pkg.genai = genai_mod
genai_mod.types = types_mod

class _Cfg:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

types_mod.GenerateContentConfig = _Cfg
types_mod.ThinkingConfig = _Cfg

class MockModels:
    def generate_content(self, model, contents, config):
        assert config.system_instruction, "system prompt missing"
        assert config.thinking_config.thinking_level == "high"
        assert "MC.PA" in contents, "market data missing from prompt"
        return types.SimpleNamespace(text="```json\n" + json.dumps({
            "decisions": [
                {"ticker": "CAC.PA", "action": "BUY", "confidence": 0.9,
                 "reason": "Strong uptrend", "max_position_pct": 25},
                {"ticker": "MC.PA", "action": "BUY", "confidence": 0.7,
                 "reason": "Breaking above MA50", "max_position_pct": 80},
            ],
            "portfolio_strategy": "Aggressive buy",
            "risk_check": "OK"
        }) + "\n```")

class MockClient:
    def __init__(self, **kwargs):
        self.models = MockModels()

genai_mod.Client = MockClient
os.environ['GEMINI_API_KEY'] = 'mock-key'

import trader

closes = [100.0 + i * 0.5 for i in range(250)]
markets = {"CAC.PA": closes, "MC.PA": [c * 4 for c in closes]}
state = {"cash": 10000.0, "equity": 10000.0, "holdings": {}}

decisions, engine = trader.get_decisions(markets, state)
assert engine == trader.GEMINI_MODEL, engine
print("Gemini API path OK:", decisions.get("portfolio_strategy"))

trades = trader.execute_orders(state, decisions, {s: p[-1] for s, p in markets.items()})
assert len(trades) == 2
# max_position_pct=80 doit être plafonné à MAX_POSITION_SIZE
assert all(t["amount"] <= 10000 * trader.MAX_POSITION_SIZE / 100 for t in trades)
trader.mark_to_market(state, {s: p[-1] for s, p in markets.items()})
assert abs(state["equity"] - 10000.0) < 1, state["equity"]
print("Orders OK:", [(t["ticker"], t["amount"]) for t in trades], "cash", state["cash"])

rules = trader.rule_based_decisions(markets, {})
print("Rule-based OK:", [(d["ticker"], d["action"]) for d in rules["decisions"]])
