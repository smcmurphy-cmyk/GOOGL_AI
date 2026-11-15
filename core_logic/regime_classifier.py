from models.market_data import OptionsChain
from models.regime import RegimeState
from utils.greeks import calculate_gex_profile

def classify_regime(
    chain: OptionsChain, 
    hv_rank: float, 
    gex_threshold: float = 5_000_000.0,
) -> RegimeState:
    
    profile = calculate_gex_profile(chain, max_dte=45, min_oi=10)
    is_tradeable = len(profile.sorted_strikes) >= 15
    
    # PHASE 1 FIX: Signed GEX testing
    if profile.net_gex >= gex_threshold:
        # Positive GEX: Dealers are long gamma. They sell rips and buy dips, pinning the market.
        regime_type = "MEAN_REVERSION"
    elif profile.net_gex <= -gex_threshold:
        # Negative GEX: Dealers are short gamma. They sell into weakness and buy into strength.
        regime_type = "DIRECTIONAL_BREAKOUT"
    else:
        # Neutral GEX lacks the structural dealer flows required for an edge.
        regime_type = "UNCERTAIN"
        
    return RegimeState(
        regime_type=regime_type,
        net_gex=profile.net_gex,
        gamma_flip=profile.gamma_flip,  
        call_wall=profile.call_wall,   
        put_wall=profile.put_wall,     
        is_tradeable=is_tradeable
    )