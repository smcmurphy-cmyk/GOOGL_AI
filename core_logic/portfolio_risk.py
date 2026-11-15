from models.alerts import ScoredPlay

def portfolio_gatekeeper(
    candidate_play: ScoredPlay, 
    session_open_risk_usd: float, 
    hv_rank: float, 
    positions_this_cycle: int,
    account_balance: float = 10000.0
) -> tuple[bool, str]:
    """
    Evaluates a candidate trade against dynamic portfolio risk constraints.
    Returns (Is_Approved, Reason).
    """
    # P1.8: Max positions per 2-minute cycle to prevent over-trading a single momentum burst
    if positions_this_cycle >= 2:
        return False, "Max positions per cycle reached."

    # P1.7: Dynamic Position Sizing based on Volatility
    # Standard risk is 1%, scale down to 0.5% if Historical Volatility is extremely high (> 80)
    max_trade_risk_pct = 0.005 if hv_rank > 80.0 else 0.01
    max_trade_risk_usd = account_balance * max_trade_risk_pct
    
    proposed_risk = candidate_play.structure.max_risk 
    
    if proposed_risk > max_trade_risk_usd:
        return False, f"Trade risk (${proposed_risk:.2f}) exceeds dynamic per-trade sizing limit (${max_trade_risk_usd:.2f})."
        
    # Standard 5% maximum daily portfolio heat limit
    max_daily_risk = account_balance * 0.05
    if (session_open_risk_usd + proposed_risk) > max_daily_risk:
        return False, f"Trade breaches maximum daily risk budget of ${max_daily_risk:.2f}."
        
    return True, "Passed"
