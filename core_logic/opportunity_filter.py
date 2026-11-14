from datetime import datetime, time
import pytz
from models.regime import RegimeState
from models.market_data import OptionsChain

def is_viable_scalp_environment(chain: OptionsChain, regime: RegimeState) -> tuple[bool, str]:
    """
    Evaluates market context (Time of Day, Momentum, Liquidity) to determine 
    if the regime presents a high-probability scalping opportunity.
    """
    # 1. Targeted Morning Trading Window (EST)
    nyc_tz = pytz.timezone('America/New_York')
    now = datetime.now(nyc_tz).time()
    
    # Set strict 9:35 AM to 11:00 AM window
    market_open = time(9, 35)
    market_close = time(11, 0)
    
    if not (market_open <= now <= market_close):
        return False, "Outside morning scalp window (9:35 AM - 11:00 AM EST)."

    # 2. Minimum Liquidity Check
    total_volume = sum(c.volume for c in chain.contracts if c.volume is not None)
    if total_volume < 1000:
        return False, f"Insufficient chain volume ({total_volume} contracts)."

    # 3. Regime Confirmation
    if regime.regime_type == "UNCERTAIN" or not regime.is_tradeable:
        return False, "Regime is UNCERTAIN or untradeable."

    return True, "Passed Context Filter"