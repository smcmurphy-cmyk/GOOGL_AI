from models.market_data import OptionsChain
from models.regime import RegimeState

# FIX: Import the new spot-sweep functions from core_logic.gex
from core_logic.gex import total_gex_at, calculate_gamma_flip 

def classify_regime(
    chain: OptionsChain, 
    hv_rank: float, 
    gex_threshold: float = 5_000_000.0,
) -> RegimeState:
    
    spot = chain.underlying.price
    
    # Filter out contracts with missing data before sweeping
    valid_contracts = [c for c in chain.contracts if c.implied_volatility and c.open_interest]
    is_tradeable = len(valid_contracts) >= 15
    
    # Use the new spot-sweep method to find the true zero-crossing
    gamma_flip = calculate_gamma_flip(valid_contracts, spot)
    
    # Calculate net GEX at the current spot price
    net_gex = total_gex_at(valid_contracts, spot)
    
    # Signed GEX testing for Regime (Macro Environment)
    if net_gex >= gex_threshold:
        regime_type = "LONG_GAMMA" # Dealers dampen moves (Pinning)
    elif net_gex <= -gex_threshold:
        regime_type = "SHORT_GAMMA" # Dealers amplify moves (Directional)
    else:
        regime_type = "NEUTRAL"
        
    return RegimeState(
        regime_type=regime_type,
        net_gex=net_gex,
        gamma_flip=gamma_flip,  
        call_wall=None,   # Optional: Implement OI-weighted search later
        put_wall=None,     
        is_tradeable=is_tradeable
    )