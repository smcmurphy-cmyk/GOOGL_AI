from models.alerts import ScoredPlay

def portfolio_gatekeeper(
    top_play: ScoredPlay, 
    session_open_risk_usd: float, 
    hv_rank: float, 
    positions_this_cycle: int, 
    account_balance: float = 10000.0
) -> tuple[bool, str]:
    
    # 1% max heat per cycle
    max_heat_usd = account_balance * 0.01 
    
    # PHASE 2 FIX: Calculate True Trade Risk based on the planned Stop Loss, not total premium
    true_trade_risk = top_play.structure.max_risk * top_play.exits.stop_loss_pct
    
    if true_trade_risk > max_heat_usd:
        return False, f"True risk ${true_trade_risk:.2f} exceeds 1% limit (${max_heat_usd:.2f})"
        
    # Cap total session exposure at 3%
    if session_open_risk_usd + true_trade_risk > (account_balance * 0.03):
        return False, "Session risk exceeds 3% daily limit"
        
    if positions_this_cycle >= 2:
        return False, "Max positions per cycle reached"
        
    return True, ""