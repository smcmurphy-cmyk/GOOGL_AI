import math
from typing import List
from models.structures import OptionStructure
from models.alerts import ScoredPlay, TradeExits # <-- Added TradeExits import
from models.regime import RegimeState

def evaluate_and_rank(structures: list[OptionStructure], regime: RegimeState, ticker: str, account_balance: float = 10000.0) -> list[ScoredPlay]:
    scored_plays = []
    
    for structure in structures:
        pop = structure.probability_of_profit if structure.probability_of_profit is not None else 0.50
        risk = structure.max_risk
        
        # Determine the short strike and DTE for Expected Move context
        short_leg = next((leg for leg in structure.legs if leg.action == "SELL"), None)
        long_leg = next((leg for leg in structure.legs if leg.action == "BUY"), None)
        
        if not short_leg:
            continue
            
        dte = max(1, (short_leg.contract.expiration - __import__('datetime').date.today()).days)
        iv = short_leg.contract.implied_volatility if short_leg.contract.implied_volatility else 0.50
        spot = short_leg.contract.underlying_price if hasattr(short_leg.contract, 'underlying_price') else short_leg.contract.strike # fallback
        
        # Calculate standard 1 Standard Deviation Expected Move
        expected_move = spot * iv * math.sqrt(dte / 365.0)
        
        if "Debit" in structure.strategy_type:
            width = abs(short_leg.contract.strike - long_leg.contract.strike) if long_leg else 0
            reward = (width * 100) - risk
        else:
            reward = structure.net_premium * 100
            
            # P3.13: Expected Move Context Penalty for Credit Spreads
            # If the short strike is within the expected move, severely penalize the PoP
            distance_to_short = abs(spot - short_leg.contract.strike)
            if distance_to_short < expected_move:
                pop *= 0.75  # 25% penalty for crowding the expected move
        
        expectancy = (pop * reward) - ((1.0 - pop) * risk)
        
        # Only accept positive expectancy trades
        if expectancy > 0:
            exits = TradeExits(
                profit_target_pct=0.50, 
                stop_loss_pct=1.00,
                time_stop_days=0,
                invalidation_level=regime.gamma_flip if regime.gamma_flip else spot
            )
            
            scored_plays.append(ScoredPlay(
                structure=structure,
                expectancy_score=expectancy,
                exits=exits
            ))
            
    # Sort highest expectancy first
    return sorted(scored_plays, key=lambda x: x.expectancy_score, reverse=True)
            
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