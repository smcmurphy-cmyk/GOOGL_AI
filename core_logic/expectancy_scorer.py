from typing import List
from models.structures import OptionStructure
from models.alerts import ScoredPlay, TradeExits # <-- Added TradeExits import
from models.regime import RegimeState

def evaluate_and_rank(
    structures: List[OptionStructure], 
    regime: RegimeState, 
    ticker: str,
    account_balance: float = 10000.0, 
    max_risk_pct: float = 0.02
) -> List[ScoredPlay]:
    
    if not structures:
        return []
        
    scored_plays = []
    allowed_risk_dollars = account_balance * max_risk_pct
        
    for structure in structures:
        pop = structure.probability_of_profit if structure.probability_of_profit is not None else 0.50
        reward = structure.net_premium
        risk = structure.max_risk
        
        expectancy = (pop * reward) - ((1.0 - pop) * risk)
        
        if expectancy > 0 and risk > 0 and risk <= allowed_risk_dollars:
            
            # --- PHASE 4: EXPLICIT EXIT TRIGGERS ---
            # Define the exact price level that breaks the structural thesis
            if "Debit" in structure.strategy_type:
                invalidation = regime.gamma_flip
            else:
                invalidation = regime.call_wall if "Call" in structure.strategy_type else regime.put_wall
                
            exits = TradeExits(
                profit_target_pct=0.50,  # Target 50% of max profit
                stop_loss_pct=1.00,      # Stop out at 1x max risk
                time_stop_days=0,        # 0 = Intraday exit for scalping
                invalidation_level=invalidation
            )
            # ---------------------------------------

            play = ScoredPlay(
                ticker=ticker,
                regime=regime,
                structure=structure,
                expectancy_score=expectancy,
                exits=exits              # <-- Passed to payload
            )
            scored_plays.append(play)

    return sorted(scored_plays, key=lambda p: p.expectancy_score, reverse=True)