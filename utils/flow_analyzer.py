from typing import List, Optional
from models.market_data import OptionContract

def check_rejection_flow(contract: OptionContract) -> bool:
    """
    Checks if a major GEX wall is seeing low relative volume,
    indicating the level will likely hold (reversal setup).
    """
    if not contract or contract.volume is None or contract.open_interest is None:
        return False
    
    vol_oi_ratio = contract.volume / max(1, contract.open_interest)
    return vol_oi_ratio < 1.0

def find_breakout_flow(contracts: List[OptionContract], spot: float, direction: str) -> Optional[OptionContract]:
    """
    Scans OTM strikes to find aggressive new volume (Vol/OI > 1.0)
    indicating dealer hedging and momentum continuation.
    """
    if not contracts:
        return None
        
    # Sort contracts to find OTM strikes closest to spot
    if direction == "up":
        # OTM Calls (strike > spot)
        otm_contracts = sorted([c for c in contracts if c.strike > spot], key=lambda c: c.strike)
    else:
        # OTM Puts (strike < spot)
        otm_contracts = sorted([c for c in contracts if c.strike < spot], key=lambda c: c.strike, reverse=True)
        
    # Scan the next 3 OTM strikes for aggressive flow
    for contract in otm_contracts[:3]:
        if contract.volume is not None and contract.open_interest is not None:
            vol_oi_ratio = contract.volume / max(1, contract.open_interest)
            if vol_oi_ratio > 1.0:
                return contract
                
    return None