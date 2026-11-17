import asyncio
import httpx
from datetime import datetime
import pytz
from typing import Dict, Any
from config.settings import config
from models.alerts import ScoredPlay
from models.regime import RegimeState

# In-memory queue for non-blocking telemetry
alert_queue = asyncio.Queue()
scan_queue = asyncio.Queue()

def _generate_alert_id(ticker: str, play: ScoredPlay) -> str:
    """Generates a deterministic hash to prevent duplicate sheet entries on retry."""
    date_str = datetime.now(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d")
    expiry = play.structure.legs[0].contract.expiration.strftime("%Y-%m-%d")
    
    # Format: 600C+/602C- (Strike, Type, Action)
    leg_parts = []
    for leg in play.structure.legs:
        c_p = "C" if leg.contract.option_type == "call" else "P"
        action = "+" if leg.action == "BUY" else "-"
        leg_parts.append(f"{leg.contract.strike}{c_p}{action}")
        
    legs_str = "/".join(leg_parts)
    strategy_clean = play.structure.strategy_type.replace(" ", "")
    
    return f"{date_str}|{ticker}|{strategy_clean}|{expiry}|{legs_str}"

def build_alert_payload(ticker: str, regime: RegimeState, play: ScoredPlay, thesis: str) -> Dict[str, Any]:
    """Constructs the strictly typed v2 JSON schema."""
    now_iso = datetime.utcnow().isoformat() + "Z"
    
    legs_payload = []
    for leg in play.structure.legs:
        legs_payload.append({
            "action": leg.action,
            "type": "C" if leg.contract.option_type == "call" else "P",
            "strike": leg.contract.strike,
            "expiry": leg.contract.expiration.strftime("%Y-%m-%d"),
            "bid": leg.contract.bid,
            "ask": leg.contract.ask,
            "delta": leg.contract.delta
        })

    return {
        "schema_version": 2,
        "alert_id": _generate_alert_id(ticker, play),
        "tab_name": "Trade Candidates",
        "quote_time": now_iso,
        "sent_time": now_iso,
        "ticker": ticker,
        "regime": regime.regime_type,
        "strategy": play.structure.strategy_type,
        "gex": {
            "net_total": regime.net_gex,
            "gamma_flip": regime.gamma_flip,
            "call_wall": regime.call_wall,
            "put_wall": regime.put_wall
        },
        "legs": legs_payload,
        "max_risk_usd": round(play.structure.max_risk, 2),
        "true_risk_usd": round(play.structure.max_risk * play.exits.stop_loss_pct, 2),
        "target_pct": play.exits.profit_target_pct,
        "stop_pct": play.exits.stop_loss_pct,
        "time_stop_minutes": play.exits.time_stop_minutes,
        "invalidation": {
            "level": play.exits.invalidation_level,
            "side": play.exits.invalidation_side
        },
        "pop": play.pop,
        "pop_source": play.pop_source,
        "net_ev_r": round(play.net_ev_r, 2),
        "paper_only": play.paper_only,
        "thesis": thesis
    }

async def enqueue_alert(ticker: str, regime: RegimeState, play: ScoredPlay, thesis: str):
    """Puts the payload into the queue instantly, returning control to the main loop."""
    payload = build_alert_payload(ticker, regime, play, thesis)
    await alert_queue.put(payload)

async def enqueue_market_scan(ticker: str, regime: RegimeState, reject_reason: str):
    payload = {
        "schema_version": 2,
        "tab_name": "Market Scans",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ticker": ticker,
        "regime": regime.regime_type,
        "reject_reason": reject_reason
    }
    await scan_queue.put(payload)

async def outbox_worker():
    """Background task that processes queues with exponential backoff retries."""
    async with httpx.AsyncClient() as client:
        while True:
            # Process alerts
            if not alert_queue.empty():
                payload = await alert_queue.get()
                await _deliver_with_retry(client, payload)
                alert_queue.task_done()
                
            # Process scans
            if not scan_queue.empty():
                payload = await scan_queue.get()
                await _deliver_with_retry(client, payload)
                scan_queue.task_done()
                
            await asyncio.sleep(0.5)

async def _deliver_with_retry(client: httpx.AsyncClient, payload: Dict[str, Any], max_retries: int = 3):
    if not getattr(config, 'webhook_url', None):
        return

    headers = {"Content-Type": "application/json"}
    if hasattr(config, 'webhook_token') and config.webhook_token:
        headers["X-Alert-Token"] = config.webhook_token

    for attempt in range(max_retries):
        try:
            response = await client.post(config.webhook_url, json=payload, headers=headers, timeout=10.0)
            if response.status_code == 200:
                return  # Success
        except httpx.RequestError as e:
            if attempt == max_retries - 1:
                print(f"[-] DEAD LETTER: Webhook failed after {max_retries} attempts: {e}")
            else:
                await asyncio.sleep(2 ** attempt) # Exponential backoff: 1s, 2s, 4s