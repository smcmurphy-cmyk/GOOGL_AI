import math
from typing import List, Optional
from models.market_data import OptionContract

def _bs_gamma(spot: float, strike: float, dte_days: float, iv: float) -> float:
    """Calculates Black-Scholes Gamma."""
    if dte_days <= 0 or iv <= 0:
        return 0.0
    
    t = dte_days / 365.0
    d1 = (math.log(spot / strike) + (0.5 * iv ** 2) * t) / (iv * math.sqrt(t))
    
    # Standard normal PDF
    pdf_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
    
    gamma = pdf_d1 / (spot * iv * math.sqrt(t))
    return gamma

def total_gex_at(contracts: List[OptionContract], hypothetical_spot: float) -> float:
    """Calculates total dealer GEX at a hypothetical underlying price."""
    total_gex = 0.0
    for c in contracts:
        if c.implied_volatility is None or c.open_interest is None:
            continue
            
        dte = max(1, (c.expiration - c.expiration.today()).days) # minimum 1 DTE for math stability
        gamma = _bs_gamma(hypothetical_spot, c.strike, dte, c.implied_volatility)
        
        # Formula: gamma * OI * 100 * spot^2 * 0.01
        # Calls are dealer-short (positive GEX), Puts are dealer-long (negative GEX)
        contract_gex = gamma * c.open_interest * 100 * (hypothetical_spot ** 2) * 0.01
        
        if c.option_type == 'put':
            contract_gex = -contract_gex
            
        total_gex += contract_gex
        
    return total_gex

def calculate_gamma_flip(contracts: List[OptionContract], spot: float, lo: float = 0.93, hi: float = 1.07, steps: int = 57) -> Optional[float]:
    """Price at which total GEX crosses zero, recomputing gamma at each hypothetical spot."""
    prices = [spot * (lo + i * (hi - lo) / (steps - 1)) for i in range(steps)]
    totals = [total_gex_at(contracts, p) for p in prices]   
    
    for (p0, g0), (p1, g1) in zip(zip(prices, totals), zip(prices[1:], totals[1:])):
        if g0 == 0 or g0 * g1 < 0:
            # Linear interpolation for exact zero crossing
            return p0 + (p1 - p0) * (-g0) / (g1 - g0)       
            
    return None # No flip inside +/-7%