from typing import List
from models.alerts import ScoredPlay
from config.settings import config

def portfolio_gatekeeper(candidate_play, session_open_risk_usd: float, account_balance: float = 10000.0) -> bool:
    max_daily_risk = account_balance * 0.05
    # Target the correct attribute inside the structure
    proposed_risk = candidate_play.structure.max_risk 
    
    if (session_open_risk_usd + proposed_risk) > max_daily_risk:
        return False
    return True
