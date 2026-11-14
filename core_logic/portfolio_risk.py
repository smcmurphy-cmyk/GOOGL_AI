from typing import List
from models.alerts import ScoredPlay
from config.settings import config

def portfolio_gatekeeper(
    candidate_play: ScoredPlay, 
    open_risk_usd: float, 
    account_balance: float = 10000.0
) -> bool:
    """
    Validates that executing the top-ranked idea will not breach the overall daily portfolio risk budget.
    """
    max_daily_risk_usd = account_balance * config.max_daily_risk_pct
    projected_total_risk = open_risk_usd + candidate_play.account_risk_usd
    
    if projected_total_risk > max_daily_risk_usd:
        # Log this internally: "Trade rejected: Portfolio daily risk budget exceeded."
        return False
        
    return True
