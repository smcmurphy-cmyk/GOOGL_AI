from models.market_data import OptionsChain
from models.regime import RegimeState
from utils.greeks import calculate_gex_profile 

def classify_regime(
    chain: OptionsChain, 
    hv_rank: float, 
    gex_threshold: float = 5_000_000.0,
    hv_threshold: float = 50.0      
) -> RegimeState:
    
    # 1. Calculate the GEX topography
    profile = calculate_gex_profile(chain, max_dte=45, min_oi=10)
    
    # 2. Minimum liquidity check
    is_tradeable = len(profile.sorted_strikes) >= 15
    
    # Positive GEX dampens moves (Mean Reversion), Negative GEX amplifies moves (Directional)
    regime_type = "UNCERTAIN"
    
# P0.2: Dual-factor logic utilizing both Net GEX and Historical Volatility Rank
    if profile.net_gex > gex_threshold and hv_rank >= hv_threshold:
        regime_type = "MEAN_REVERSION"
    elif profile.net_gex < -gex_threshold and hv_rank < hv_threshold:
        regime_type = "DIRECTIONAL_BREAKOUT"
        
    return RegimeState(
        regime_type=regime_type,
        net_gex=profile.net_gex,
        gamma_flip=profile.gamma_flip,
        call_wall=profile.call_wall,   
        put_wall=profile.put_wall,     
        is_tradeable=is_tradeable
    )