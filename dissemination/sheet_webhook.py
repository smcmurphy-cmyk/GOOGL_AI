import httpx
import aiohttp
from datetime import datetime, timezone
from models.alerts import ScoredPlay
from models.regime import RegimeState
from config.settings import config

async def post_to_sheet(ticker: str, regime: RegimeState, play: ScoredPlay, thesis: str) -> bool:
    if not config.webhook_url:
        print("[-] Webhook URL not configured.")
        return False

    # PHASE 4 FIX: Idempotent Alert ID ensures network retries do not create duplicate rows
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # Build a strike string (e.g., "450.0C-455.0C" or "240.5P")
    strike_parts = []
    for leg in play.structure.legs:
        call_put = "C" if leg.contract.option_type == "call" else "P"
        strike_parts.append(f"{leg.contract.strike}{call_put}")
    strike_str = "-".join(strike_parts)
    
    strategy_clean = play.structure.strategy_type.replace(" ", "")
    
    alert_id = f"{date_str}-{ticker}-{strategy_clean}-{strike_str}"

    # PHASE 4 FIX: Correct payload mapping for realistic expectancy tracking
    payload = {
        "alert_id": alert_id,
        "timestamp": datetime.utcnow().isoformat(),
        "ticker": ticker,
        "regime": regime.regime_type,
        "net_gex": regime.net_gex,
        "strategy": play.structure.strategy_type,
        "entry_premium": play.structure.net_premium,
        "max_risk_usd": play.structure.max_risk,
        
        # Mapped correctly as expected dollar value, freeing up the R-multiple column for post-trade tracking
        "expected_value_usd": round(play.expectancy_score, 2), 
        
        "target_pct": play.exits.profit_target_pct,
        "stop_pct": play.exits.stop_loss_pct,
        "time_stop_minutes": play.exits.time_stop_minutes, # Missing field injected
        "invalidation_level": play.exits.invalidation_level,
        "thesis": thesis,
        
        # Leave outcomes explicitly blank for the manual feedback loop
        "realized_r": "", 
        "exit_reason": "",
        "status": "OPEN"
    }

    try:
        async with aiohttp.ClientSession() as session:
            # 10-second timeout prevents the webhook from blocking the event loop
            async with session.post(config.webhook_url, json=payload, timeout=10) as response:
                return response.status == 200
    except Exception as e:
        print(f"[-] Webhook transmission failed: {e}")
        return False


async def post_market_scan(ticker: str, regime: RegimeState, reject_reason: str) -> bool:
    """
    POSTs rejected opportunities directly to the Market Scans tab.
    """
    payload = {
        "tab_name": "Market Scans",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker,
        "regime": regime.regime_type,
        "net_gex": round(regime.net_gex, 2),
        "reject_reason": reject_reason
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(config.webhook_url, json=payload, timeout=10.0)
            response.raise_for_status()
            return True
    except Exception as e:
        print(f"  [Debug] Market Scan POST failed for {ticker}: {e}")
        return False