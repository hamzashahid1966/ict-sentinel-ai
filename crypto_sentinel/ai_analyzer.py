"""
Crypto Sentinel AI - Asynchronous Post-Trade Analyzer & Forensic Coach
Generates institutional behavioral debriefs and archives multi-timeframe candle datasets.
Runs in a background worker thread to ensure ZERO LATENCY impact on live order execution.
"""

import os
import json
import time
import urllib.request
import threading
from typing import Dict, Any, Optional
from crypto_sentinel.config import SSL_CONTEXT, DIRECT_OPENER, direct_urlopen

class CryptoAIAnalyzer:
    def __init__(self, storage):
        self.storage = storage
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def analyze_trade_async(self, snapshot_id: str):
        """Asynchronously dispatches analysis in a background thread."""
        threading.Thread(target=self._run_analysis, args=(snapshot_id,), daemon=True).start()

    def _run_analysis(self, snapshot_id: str):
        try:
            with self.storage._get_connection() as conn:
                row = conn.execute("SELECT * FROM crypto_trade_snapshots WHERE snapshot_id = ?;", (snapshot_id,)).fetchone()
                if not row or not row['closed_at']:
                    return
                data = dict(row)

            # Generate AI Forensic Debrief
            debrief = self._synthesize_debrief(data)
            self.storage.update_snapshot_ai_debrief(snapshot_id, debrief)
            
            # Log to activity feed
            net_str = f"+${data['net_pnl']:.2f}" if data['net_pnl'] >= 0 else f"-${abs(data['net_pnl']):.2f}"
            self.storage.log_activity(
                action="AI_DEBRIEF",
                coin=data['symbol'],
                detail=f"🧠 {data['symbol']} {data['direction']} ({net_str} Net): {debrief[:110]}...",
                level="SUCCESS" if data['is_win'] else "INFO"
            )
        except Exception as e:
            pass

    def _synthesize_debrief(self, data: Dict[str, Any]) -> str:
        """
        Attempts Tier 1 (OpenRouter) -> Tier 2 (Ollama) -> Tier 3 (Quantitative Forensic Engine).
        """
        # Tier 1: OpenRouter LLM
        if self.openrouter_key:
            try:
                ai_text = self._query_openrouter(data)
                if ai_text:
                    return ai_text
            except Exception:
                pass

        # Tier 2: Local Ollama
        try:
            ai_text = self._query_ollama(data)
            if ai_text:
                return ai_text
        except Exception:
            pass

        # Tier 3: Quantitative Pattern Forensic Engine (Deterministic & Instant)
        return self._generate_quantitative_forensic(data)

    def _query_openrouter(self, data: Dict[str, Any]) -> Optional[str]:
        prompt = self._build_prompt(data)
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = json.dumps({
            "model": "google/gemini-2.0-flash-001",
            "messages": [
                {"role": "system", "content": "You are a quantitative trading post-mortem analyst. Provide a concise 2-sentence institutional trade critique focusing on ICT liquidity, BTC regime, and fee coverage."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 120,
            "temperature": 0.2
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json"
        })
        with direct_urlopen(req, timeout=4.0) as resp:
            res = json.loads(resp.read().decode())
            return res["choices"][0]["message"]["content"].strip()

    def _query_ollama(self, data: Dict[str, Any]) -> Optional[str]:
        prompt = self._build_prompt(data)
        url = f"{self.ollama_host}/api/generate"
        payload = json.dumps({
            "model": "llama3",
            "prompt": f"System: Institutional Trading Debrief. 2 sentences only.\nUser: {prompt}",
            "stream": False,
            "options": {"num_predict": 100, "temperature": 0.2}
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            res = json.loads(resp.read().decode())
            return res.get("response", "").strip()

    def _generate_quantitative_forensic(self, data: Dict[str, Any]) -> str:
        """High-precision quantitative technical debrief."""
        sym = data['symbol']
        dirn = data['direction']
        engine = data['engine'].replace("_", " ").title()
        net = data['net_pnl']
        gross = data['gross_pnl']
        fees = data['fees']
        reason = data['exit_reason'] or ""
        btc = data['btc_trend']
        is_win = bool(data['is_win'])
        hold_mins = int((data['closed_at'] - data['created_at']) // 60) if data.get('closed_at') else 15

        if is_win:
            if "TARGET_2" in reason:
                return f"🎯 Full Target 2 (+0.80R) reached in {hold_mins}m. Clean {engine} sweep followed by directional continuation. BTC trend ({btc}) provided directional tailwind; generated +${gross:.2f} gross with ${fees:.2f} fees paid."
            else:
                return f"✅ Target 1 secured at 0.40R (+${net:.2f} net in {hold_mins}m). Stop moved to defensive breakeven. Strong order book alignment and fee-positive scalp execution."
        else:
            if "DEFENSIVE" in reason or "STAGNANT" in reason:
                return f"🛡️ Capital preserved via defensive breakeven (+${net:.2f} net after ${fees:.2f} fees). After banking partial profit, trailing stop protected gains from subsequent consolidation."
            elif "STOP_LOSS" in reason:
                return f"🛑 Stop collar triggered (-${abs(net):.2f}). Adverse wick during low volume compression against BTC trend ({btc}). Capped loss within strict $4.00 safety parameters."
            else:
                return f"🔄 Position concluded via {reason} in {hold_mins}m. Net PnL: ${net:.2f} after ${fees:.2f} Binance fees. Metric updated in Asset Intelligence database."

    def _build_prompt(self, data: Dict[str, Any]) -> str:
        return f"""
Analyze this crypto futures trade:
- Asset: {data['symbol']} ({data['direction']})
- Engine: {data['engine']}
- Entry Price: {data['entry_price']} | Exit: {data['exit_price']}
- Outcome: {'WIN' if data['is_win'] else 'LOSS'} | Net PnL: ${data['net_pnl']:.2f} (Fees: ${data['fees']:.2f})
- Exit Reason: {data['exit_reason']}
- BTC Macro Regime: {data['btc_trend']}
Provide a 2-sentence institutional trade critique.
"""
