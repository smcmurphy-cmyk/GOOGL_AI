import math
import datetime
from models.structures import OptionStructure
from models.regime import RegimeState
from models.alerts import ScoredPlay, TradeExits

def evaluate_and_rank(structures: list[OptionStructure], regime: RegimeState, ticker: str, spot: float) -> list[ScoredPlay]:
    scored_plays = []
    
    for structure in structures:
        pop = structure.probability_of_profit if structure.probability_of_profit is not None else 0.50
        
        short_leg = next((leg for leg in structure.legs if leg.action == "SELL"), None)
        long_leg = next((leg for leg in structure.legs if leg.action == "BUY"), None)
        
        # Use whichever leg exists to extract volatility context
        ref_contract = short_leg.contract if short_leg else long_leg.contract
        if not ref_contract: 
            continue
            
        dte = max(1, (ref_contract.expiration - datetime.date.today()).days)
        iv = ref_contract.implied_volatility if ref_contract.implied_volatility else 0.50
        
        # P0 FIX: Use the actual underlying spot price passed from the chain, removing the fallback to strike
        expected_move = spot * iv * math.sqrt(dte / 365.0)
        
        is_naked_long = "Long Call" in structure.strategy_type or "Long Put" in structure.strategy_type
        
        # P0 FIX: Define actual trading exits (50% target for spreads, 150% for naked longs)
        target_pct = 1.50 if is_naked_long else 0.50
        stop_pct = 1.00
        
        # P0 FIX: Calculate expectancy based on PLANNED exits, not theoretical max width
        if is_naked_long or "Debit" in structure.strategy_type:
            max_risk = structure.max_risk
            reward = max_risk * target_pct
            actual_risk = max_risk * stop_pct
        else: # Credit Spreads
            max_reward = structure.net_premium * 100
            reward = max_reward * target_pct
            actual_risk = max_reward * stop_pct
            
            # Expected Move Context Penalty (Only applies to Credit Spreads with short strikes)
            if short_leg:
                distance_to_short = abs(spot - short_leg.contract.strike)
                if distance_to_short < expected_move:
                    pop *= 0.75  
        
        expectancy = (pop * reward) - ((1.0 - pop) * actual_risk)
        
        # Only accept positive expectancy trades
        if expectancy > 0:
            exits = TradeExits(
                profit_target_pct=target_pct, 
                stop_loss_pct=stop_pct,
                time_stop_days=0,
                invalidation_level=regime.gamma_flip if regime.gamma_flip else spot
            )
            
            scored_plays.append(ScoredPlay(
                ticker=ticker,
                regime=regime,
                structure=structure,
                expectancy_score=expectancy,
                exits=exits
            ))
            
    # Sort highest expectancy first
    return sorted(scored_plays, key=lambda x: x.expectancy_score, reverse=True)