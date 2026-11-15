import httpx
from datetime import datetime, timezone
from models.alerts import ScoredPlay
from models.regime import RegimeState
from config.settings import config

async def post_to_sheet(
    ticker: str, 
    regime: RegimeState, 
    play: ScoredPlay, 
    thesis: str
) -> bool:
    """
    Formats the trade data into the flat JSON schema and POSTs it to the webhook.
    """
    strategy = play.structure.strategy_type.replace('_', ' ').title()
    
    # Safely extract legs from the OptionStructure schema
    short_leg = next((leg for leg in play.structure.legs if leg.action == "SELL"), None)
    long_leg = next((leg for leg in play.structure.legs if leg.action == "BUY"), None)
    
    # Handle both Spreads and Naked Longs/Shorts
    if short_leg and long_leg:
        contracts_str = f"+1 {long_leg.contract.strike} / -1 {short_leg.contract.strike}"
        dte = (long_leg.contract.expiration - datetime.now().date()).days
    elif long_leg:
        contracts_str = f"Long {long_leg.contract.strike}"
        dte = (long_leg.contract.expiration - datetime.now().date()).days
    elif short_leg:
        contracts_str = f"Short {short_leg.contract.strike}"
        dte = (short_leg.contract.expiration - datetime.now().date()).days
    else:
        contracts_str = "N/A"
        dte = 0

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    alert_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{ticker}-{strategy.replace(' ', '')}"
    
    target_exit = play.exits.profit_target_pct if play.exits else 0.50
    stop_loss = play.exits.stop_loss_pct if play.exits else 1.00
    invalidation = play.exits.invalidation_level if play.exits else "N/A"

    payload = {
        "tab_name": "Trade Candidates",
        "alert_id": alert_id,
        "timestamp": timestamp,
        "ticker": ticker,
        "regime": f"{regime.regime_type} (Net GEX: {regime.net_gex:,.0f})",
        "structure": strategy,
        "contracts": contracts_str,
        "dte": dte,
        "entry_premium": round(play.structure.net_premium, 2),
        "max_risk_usd": round(play.structure.max_risk, 2),
        "planned_target": target_exit,
        "planned_stop": stop_loss,
        "invalidation": invalidation,
        "status": "OPEN",
        "actual_exit_premium": None,
        "exit_timestamp": None,
        "exit_reason": None,
        "realized_r": None,
        "realized_pnl_usd": None,
        "r_multiple": round(play.expectancy_score, 2),
        "notes": thesis 
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(config.webhook_url, json=payload, timeout=10.0)
            response.raise_for_status()
            return True
    except Exception as e:
        print(f"Webhook POST failed for {ticker}: {e}")
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