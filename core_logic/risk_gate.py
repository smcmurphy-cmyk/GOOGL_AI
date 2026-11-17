from models.alerts import ScoredPlay

def portfolio_gatekeeper(
    top_play: ScoredPlay, 
    session_heat_usd: float, 
    positions_this_cycle: int, 
    account_balance: float = 10000.0,
    max_trade_risk_pct: float = 0.01,
    max_daily_risk_pct: float = 0.03,
    max_spread_pct: float = 0.15
) -> tuple[bool, str]:
    
    # 1. Spread Width Limit (Slippage Defense)
    # Reject the trade if the bid/ask spread is wider than 15% of the total premium
    total_premium = abs(top_play.structure.net_premium)
    if total_premium > 0:
        spread_width = sum(leg.contract.ask - leg.contract.bid for leg in top_play.structure.legs)
        if (spread_width / total_premium) > max_spread_pct:
            return False, f"SPREAD_PCT: Spread width ({spread_width:.2f}) exceeds {max_spread_pct*100}% of premium."

    # 2. Calculate True Risk (Max Loss at Stop)
    true_trade_risk_usd = top_play.structure.max_risk * top_play.exits.stop_loss_pct
    
    # 3. Single Trade Risk Gate
    max_heat_per_trade = account_balance * max_trade_risk_pct
    if true_trade_risk_usd > max_heat_per_trade:
        return False, f"TRUE_RISK: Trade risk ${true_trade_risk_usd:.2f} exceeds 1% limit (${max_heat_per_trade:.2f})"
        
    # 4. Session Heat Gate
    max_daily_heat = account_balance * max_daily_risk_pct
    if session_heat_usd + true_trade_risk_usd > max_daily_heat:
        return False, f"SESSION_HEAT: Adding ${true_trade_risk_usd:.2f} exceeds 3% daily limit (${max_daily_heat:.2f})"
        
    # 5. Concurrency Limit
    if positions_this_cycle >= 2:
        return False, "CONCURRENCY: Max positions per cycle reached."
        
    return True, ""