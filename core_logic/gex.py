import math
from datetime import datetime
import pytz
from typing import List, Optional
from models.market_data import OptionContract

def _bs_gamma(spot: float, strike: float, dte_years: float, iv: float) -> float:
    """Calculates Black-Scholes Gamma."""
    if dte_years <= 0 or iv <= 0:
        return 0.0
    
    d1 = (math.log(spot / strike) + (0.5 * iv ** 2) * dte_years) / (iv * math.sqrt(dte_years))
    pdf_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
    
    gamma = pdf_d1 / (spot * iv * math.sqrt(dte_years))
    return gamma

def get_fractional_years(expiration_date) -> float:
    """Calculates precise fractional years until 16:00 ET on expiration day."""
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    
    # Set expiration precisely to 16:00 ET on the target date
    exp_dt = eastern.localize(datetime.combine(expiration_date, datetime.min.time().replace(hour=16, minute=0)))
    
    delta_seconds = (exp_dt - now).total_seconds()
    if delta_seconds <= 0:
        return 0.0001 # Prevent division by zero for actively expiring contracts
        
    return delta_seconds / (365.25 * 24 * 3600)

def total_gex_at(contracts: List[OptionContract], hypothetical_spot: float) -> float:
    """Calculates total dealer GEX at a hypothetical underlying price."""
    total_gex = 0.0
    for c in contracts:
        if c.implied_volatility is None or c.open_interest is None:
            continue
            
        # Refinement: Cap the GEX evaluation to 7 DTE. Beyond this, gamma is negligible for scalping.
        if (c.expiration - c.expiration.today()).days > 7:
            continue
            
        dte_years = get_fractional_years(c.expiration)
        
        # Refinement: Schwab IV is a percentage (e.g., 15.62). Divide by 100 for BS math.
        iv = c.implied_volatility / 100.0
        
        gamma = _bs_gamma(hypothetical_spot, c.strike, dte_years, iv)
        
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
            return p0 + (p1 - p0) * (-g0) / (g1 - g0)       
            
    return None