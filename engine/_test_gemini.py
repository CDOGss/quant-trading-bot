# -*- coding: utf-8 -*-
"""Test le chemin Gemini avec un mock du SDK, sans clé réelle."""
import sys
import types
import json
import os

google_pkg  = types.ModuleType('google')
genai_mod   = types.ModuleType('google.generative_ai')
client_mod  = types.ModuleType('google.generative_ai.client')
sys.modules['google'] = google_pkg
sys.modules['google.generative_ai'] = genai_mod
sys.modules['google.generative_ai.client'] = client_mod

class MockResp:
    def __init__(self, text):
        self.text = text

class MockClient:
    def __init__(self, **kwargs):
        pass
    def generate_text(self, prompt, **kwargs):
        return MockResp(json.dumps({
            "decisions": [
                {"ticker": "6C40", "action": "BUY", "confidence": 0.9,
                 "reason": "Strong uptrend", "max_position_pct": 25},
                {"ticker": "AX.P", "action": "BUY", "confidence": 0.7,
                 "reason": "Breaking above MA50", "max_position_pct": 25}
            ],
            "portfolio_strategy": "Aggressive buy",
            "risk_check": "OK"
        }))

genai_mod.client = client_mod
client_mod.GenerativeAIClient = MockClient
os.environ['GEMINI_API_KEY'] = 'mock-key'

import trader
result = trader.ask_gemini(
    trader.build_system_prompt(),
    trader.build_user_prompt(
        {"6C40": [100.0, 102.0, 105.0],
         "AX.P": [90.0, 92.0, 95.0]},
        {}, 10000.0, 10000.0,
        "gemini-3.8-flash", "high")
)
print("Gemini API path OK:", result.get("portfolio_strategy"))
print("Decisions:", len(result.get("decisions", [])))
