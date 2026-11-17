from typing import List, Optional
from models.structures import OptionStructure
from models.regime import RegimeState
from core_logic.strategy_selector import StrategyIntent
from pydantic import BaseModel

class TradeExits(BaseModel):
    profit_target_pct: float
    stop_loss_pct: float
    time_stop_minutes: int
    invalidation_level: float
    invalidation_side: str # "above" or "below"

class ScoredPlay(BaseModel):
    ticker: str
    regime: str
    intent: StrategyIntent
    structure: OptionStructure
    expectancy_score_usd: float
    net_ev_r: float
    pop: float
    pop_source: str
    paper_only: bool
    exits: TradeExits

def calculate_costs(structure: OptionStructure) -> float:
    """Calculates round-trip costs including commissions and bid/ask slippage."""
    commission_per_leg = 0.65 
    total_commission = sum(len(structure.legs) * commission_per_leg * 2 for _ in structure.legs)
    
    # Slippage estimate: Assume crossing the spread on both entry and exit.
    # At 09:32 ET, this spread penalty will aggressively filter out bad trades.
    total_slippage = sum((leg.contract.ask - leg.contract.bid) * 100 for leg in structure.legs)
    
    return total_commission + total_slippage

def evaluate_and_rank(structures: List[OptionStructure], regime: RegimeState, ticker: str, spot: float, intent: StrategyIntent) -> List[ScoredPlay]:
    scored_plays = []
    
    for structure in structures:
        is_naked = "Scalp" in structure.strategy_type
        
        # 1. Define Strict Exits
        target_pct = 1.50 if is_naked else 0.50
        stop_pct = 0.25 if is_naked else 1.00
        time_stop = 15 if is_naked else 120
        
        invalidation_level = regime.gamma_flip if regime.gamma_flip else spot
        invalidation_side = "below" if intent.direction == "UP" else "above"
        
        # 2. Probability of Profit (PoP)
        # Tagged strictly as BARRIER_MODEL until you replace this with empirical hit-rates.
        pop = 0.20 if is_naked else (1.0 - abs(structure.legs[0].contract.delta or 0.50))
        pop_source = "BARRIER_MODEL"
        
        # 3. True Risk and Reward Calculations
        true_risk_usd = structure.max_risk * stop_pct
        reward_usd = abs(structure.net_premium) * 100 * target_pct if not is_naked else structure.max_risk * target_pct
        
        round_trip_costs = calculate_costs(structure)
        
        # 4. Net Expected Value (EV) Formula
        net_ev_usd = (pop * reward_usd) - ((1 - pop) * true_risk_usd) - round_trip_costs
        
        # Avoid division by zero on corrupted data
        if true_risk_usd <= 0:
            continue
            
        net_ev_r = net_ev_usd / true_risk_usd
        
        # 5. Filter for Positive Edge
        if net_ev_r > 0:
            exits = TradeExits(
                profit_target_pct=target_pct,
                stop_loss_pct=stop_pct,
                time_stop_minutes=time_stop,
                invalidation_level=invalidation_level,
                invalidation_side=invalidation_side
            )
            
            scored_plays.append(ScoredPlay(
                ticker=ticker,
                regime=regime.regime_type,
                intent=intent,
                structure=structure,
                expectancy_score_usd=net_ev_usd,
                net_ev_r=net_ev_r,
                pop=pop,
                pop_source=pop_source,
                paper_only=True, # Safety toggle enabled
                exits=exits
            ))
            
    # Rank by R-Multiple, not raw dollars
    return sorted(scored_plays, key=lambda x: x.net_ev_r, reverse=True)