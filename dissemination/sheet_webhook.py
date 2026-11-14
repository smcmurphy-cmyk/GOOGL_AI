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
    # Extract readable string representations for the structure
    strategy = play.structure.strategy_type.replace('_', ' ').title()
    if hasattr(play.structure, 'short_leg'):
        contracts_str = f"+1 {play.structure.long_leg.strike} / -1 {play.structure.short_leg.strike}"
        dte = (play.structure.long_leg.expiration - datetime.now().date()).days
    else:
        contracts_str = f"Target {play.structure.contract.strike}"
        dte = (play.structure.contract.expiration - datetime.now().date()).days

    # Build the flat JSON payload matching the Google Sheet columns
    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker,
        "regime": f"{regime.regime_type} (Net GEX: {regime.net_gex:,.0f})",
        "structure": strategy,
        "contracts": contracts_str,
        "dte": dte,
        "iv_rank": round(regime.iv_rank, 2) if regime.iv_rank else None,
        "entry_premium": round(play.structure.entry_premium, 2) if hasattr(play.structure, 'entry_premium') else 0.0,
        "max_risk_usd": round(play.account_risk_usd, 2),
        "target_exit_usd": round(play.structure.target_exit_premium, 2) if hasattr(play.structure, 'target_exit_premium') else None,
        "invalidation_usd": round(play.structure.stop_loss_premium, 2) if hasattr(play.structure, 'stop_loss_premium') else 0.0,
        "status": "OPEN",
        "actual_exit_usd": None,
        "r_multiple": round(play.score, 2),
        "exit_reason": thesis 
    }

    try:
        # FIX: Added follow_redirects=True to handle Google Apps Script 302 responses
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(config.webhook_url, json=payload, timeout=10.0)
            response.raise_for_status()
            return True
    except Exception as e:
        print(f"Webhook POST failed for {ticker}: {e}")
        return False