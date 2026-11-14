from models.market_data import OptionsChain
from models.regime import RegimeState
from utils.greeks import calculate_gex_profile, calculate_iv_rank  # FIX: Correct import

def classify_regime(
    chain: OptionsChain, 
    historical_iv_low: float, 
    historical_iv_high: float,
    gex_threshold: float = 5_000_000.0,
    iv_rank_threshold: float = 50.0      
) -> RegimeState:
    
    # 1. Calculate Core Metrics using the new profile object
    profile = calculate_gex_profile(chain, max_dte=45, min_oi=10)
    
    # --- DIAGNOSTIC LOGS ---
    # (Assuming chain.underlying is successfully parsed as an object by Pydantic; 
    # if you get an error here, change it to chain.underlying.get('price'))
    print(f"  [Debug] Underlying Price: ${chain.underlying.price:,.2f}")
    print(f"  [Debug] Total Contracts Fetched: {len(chain.contracts)}")
    print(f"  [Debug] Net GEX Calculated: ${profile.net_gex:,.0f}")
    print(f"  [Debug] Gamma Flip Line: ${profile.gamma_flip}")
    print(f"  [Debug] Call Wall: ${profile.call_wall} | Put Wall: ${profile.put_wall}")
    # -----------------------

    front_month_atm_iv = next(
        (c.implied_volatility for c in chain.contracts 
         if c.implied_volatility > 0 and abs(c.strike - chain.underlying.price) / chain.underlying.price < 0.02), 
        0.30
    )
    
    iv_rank = calculate_iv_rank(front_month_atm_iv, historical_iv_low, historical_iv_high)

    # Decision logic gate with minimum liquidity check
    regime_type = "UNCERTAIN"
    
    if len(chain.contracts) >= 15:
        if profile.net_gex < -gex_threshold:
            regime_type = "DIRECTIONAL_BREAKOUT"
        elif profile.net_gex > gex_threshold:
            # Separate High IV (Mean Reversion) from Low IV (Pinned/Slow Grind)
            if iv_rank is not None and iv_rank > iv_rank_threshold:
                regime_type = "MEAN_REVERSION"
            else:
                regime_type = "PINNED_BULLISH"

    return RegimeState(
        regime_type=regime_type,
        net_gex=profile.net_gex,
        iv_rank=iv_rank,
        is_tradeable=(regime_type != "UNCERTAIN"), 
        primary_pin_strike=profile.primary_pin_strike,        
        volatility_wall_strike=profile.volatility_wall_strike,
        call_wall=profile.call_wall,   # FIX: Added new field
        put_wall=profile.put_wall,     # FIX: Added new field
        gamma_flip=profile.gamma_flip  # FIX: Added new field
    )