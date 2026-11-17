from datetime import datetime, time
import pytz
from models.market_data import OptionsChain
from models.regime import RegimeState

def is_viable_scalp_environment(chain: OptionsChain, regime: RegimeState) -> tuple[bool, str]:
    """Determines if the macro environment and time of day are viable for trading."""
    eastern = pytz.timezone('US/Eastern')
    now_et = datetime.now(eastern).time()
    
    # PHASE 3 FIX: Open window at 9:30 ET to catch opening bell breakouts
    market_open = time(9, 30)
    market_close = time(11, 0)
    
    if not (market_open <= now_et <= market_close):
        return False, f"TIME_WINDOW: Outside prime scalp window ({now_et.strftime('%H:%M:%S ET')})"
        
    if not regime.is_tradeable:
        return False, "LIQUIDITY: Regime classified as un-tradeable (insufficient valid contracts)."
        
    return True, ""