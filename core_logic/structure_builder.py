from typing import List
from models.market_data import OptionsChain
from models.regime import RegimeState
from models.structures import OptionStructure, Leg
from datetime import date
def generate_structures(chain: OptionsChain, regime: RegimeState) -> List[OptionStructure]:
    """
    Constructs defined-risk vertical spreads using GEX Topography mapping.
    """
    structures = []
    
# We want 0-3 DTE for precision scalping
    target_dte = 3 
    today = date.today()
    
    # FIX: Cleaned up the date math so it doesn't trip on string formatting
    valid_calls = [c for c in chain.contracts if c.option_type == "call" and (c.expiration - today).days <= target_dte]
    valid_puts = [c for c in chain.contracts if c.option_type == "put" and (c.expiration - today).days <= target_dte]
    if not valid_calls or not valid_puts:
        return structures

    # ---------------------------------------------------------
    # REGIME: MEAN REVERSION or PINNED (Fading the extremes)
    # ---------------------------------------------------------
    if regime.regime_type in ["MEAN_REVERSION", "PINNED_BULLISH", "PINNED_BEARISH"]:
        # In a pinned regime, dealers suppress volatility. We sell premium outside the walls.
        
        # 1. Bear Call Credit Spread (Fading the Call Wall)
        if regime.call_wall:
            short_call = next((c for c in valid_calls if c.strike == regime.call_wall), None)
            long_call = next((c for c in valid_calls if c.strike == regime.call_wall + 5.0), None)
            
            if short_call and long_call and short_call.bid > 0.0:
                structures.append(OptionStructure(
                    strategy_type="Bear Call Spread",
                    legs=[
                        Leg(contract=short_call, action="SELL", ratio=1),
                        Leg(contract=long_call, action="BUY", ratio=1)
                    ],
                    net_premium=(short_call.bid - long_call.ask),
                    max_risk=(5.0 - (short_call.bid - long_call.ask)) * 100,
                    probability_of_profit=1.0 - abs(short_call.delta)
                ))
                
        # 2. Bull Put Credit Spread (Fading the Put Wall)
        if regime.put_wall:
            short_put = next((c for c in valid_puts if c.strike == regime.put_wall), None)
            long_put = next((c for c in valid_puts if c.strike == regime.put_wall - 5.0), None)
            
            if short_put and long_put and short_put.bid > 0.0:
                structures.append(OptionStructure(
                    strategy_type="Bull Put Spread",
                    legs=[
                        Leg(contract=short_put, action="SELL", ratio=1),
                        Leg(contract=long_put, action="BUY", ratio=1)
                    ],
                    net_premium=(short_put.bid - long_put.ask),
                    max_risk=(5.0 - (short_put.bid - long_put.ask)) * 100,
                    probability_of_profit=1.0 - abs(short_put.delta)
                ))

    # ---------------------------------------------------------
    # REGIME: DIRECTIONAL BREAKOUT (Riding the momentum)
    # ---------------------------------------------------------
    elif regime.regime_type == "DIRECTIONAL_BREAKOUT":
        # In a breakout, dealers are short gamma and amplify the move. 
        # We buy debit spreads crossing the Gamma Flip line.
        
        if regime.gamma_flip:
           # FIX: Swapped .get() for standard dot notation
            spot = chain.underlying.price
            
            # If price is dropping below the flip line (Bearish Breakout)
            if spot < regime.gamma_flip:
                long_put = next((c for c in valid_puts if c.strike == regime.gamma_flip), None)
                short_put = next((c for c in valid_puts if c.strike == regime.gamma_flip - 5.0), None)
                
                if long_put and short_put and long_put.ask > 0.0:
                    cost = (long_put.ask - short_put.bid)
                    if cost < 5.0: # Ensure valid spread pricing
                        structures.append(OptionStructure(
                            strategy_type="Bear Put Debit Spread",
                            legs=[
                                Leg(contract=long_put, action="BUY", ratio=1),
                                Leg(contract=short_put, action="SELL", ratio=1)
                            ],
                            net_premium=-cost,
                            max_risk=cost * 100,
                            probability_of_profit=abs(long_put.delta)
                        ))

    return structures