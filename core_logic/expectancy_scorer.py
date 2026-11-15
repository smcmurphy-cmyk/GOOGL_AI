import math
import datetime
from models.structures import OptionStructure
from models.regime import RegimeState
from models.alerts import ScoredPlay, TradeExits

def evaluate_and_rank(structures: list[OptionStructure], regime: RegimeState, ticker: str) -> list[ScoredPlay]:
    scored_plays = []
    
    for structure in structures:
        pop = structure.probability_of_profit if structure.probability_of_profit is not None else 0.50
        risk = structure.max_risk
        
        short_leg = next((leg for leg in structure.legs if leg.action == "SELL"), None)
        long_leg = next((leg for leg in structure.legs if leg.action == "BUY"), None)
        
        # Use whichever leg exists to extract spot and volatility context
        ref_contract = short_leg.contract if short_leg else long_leg.contract
        if not ref_contract: 
            continue
            
        dte = max(1, (ref_contract.expiration - datetime.date.today()).days)
        iv = ref_contract.implied_volatility if ref_contract.implied_volatility else 0.50
        spot = ref_contract.underlying_price if hasattr(ref_contract, 'underlying_price') else ref_contract.strike 
        
        expected_move = spot * iv * math.sqrt(dte / 365.0)
        
        is_naked_long = "Long Call" in structure.strategy_type or "Long Put" in structure.strategy_type
        
        if is_naked_long:
            # Peg the expectancy reward to a conservative 150% ROI for short-dated breakout scalps
            reward = risk * 1.5 
        elif "Debit" in structure.strategy_type:
            width = abs(short_leg.contract.strike - long_leg.contract.strike) if long_leg and short_leg else 0
            reward = (width * 100) - risk
        else:
            reward = structure.net_premium * 100
            
            # Expected Move Context Penalty (Only applies to Credit Spreads with short strikes)
            if short_leg:
                distance_to_short = abs(spot - short_leg.contract.strike)
                if distance_to_short < expected_move:
                    pop *= 0.75  
        
        expectancy = (pop * reward) - ((1.0 - pop) * risk)
        
        # Only accept positive expectancy trades
        if expectancy > 0:
            exits = TradeExits(
                profit_target_pct=1.50 if is_naked_long else 0.50, 
                stop_loss_pct=1.00,
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