import httpx
import asyncio
import pandas as pd
import pytz
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from dataclasses import dataclass
from models.market_data import OptionsChain, OptionContract
from config.settings import config
import base64

@dataclass
class DailyLevels:
    prior_high: float
    prior_close: float
    pm_high: Optional[float]
    pm_low: Optional[float]
    rth_open: Optional[float]

def build_2m(df1m: pd.DataFrame) -> pd.DataFrame:
    """Aggregates 1-minute raw data into 2-minute bars aligned to the clock."""
    agg_rules = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    df2m = df1m.resample("2min", origin="start_day", label="left", closed="left").agg(agg_rules)
    return df2m.dropna(subset=["open"])

def extract_levels_and_baseline(bars_2m: pd.DataFrame, target_timestamp: pd.Timestamp) -> Tuple[Optional[DailyLevels], pd.DataFrame]:
    """Slices RTH vs ETH to extract exact support/resistance levels and calculates the RTH volume baseline."""
    target_date = target_timestamp.date()
    
    # 1. RTH Volume Baseline (09:30 to 15:59 ET)
    rth_bars = bars_2m.between_time("09:30", "15:59")
    vol_mean = rth_bars["volume"].rolling(window=975, min_periods=1).mean()
    vol_std = rth_bars["volume"].rolling(window=975, min_periods=1).std(ddof=0)
    rth_vol_stats = pd.DataFrame({"vol_mean": vol_mean, "vol_std": vol_std}, index=rth_bars.index)
    
    # 2. Prior Day RTH Levels
    unique_dates = sorted({d for d in rth_bars.index.date if d < target_date})
    if not unique_dates:
        return None, rth_vol_stats
        
    prior_date = unique_dates[-1]
    prior_session = rth_bars[rth_bars.index.date == prior_date]
    prior_high = float(prior_session["high"].max())
    prior_close = float(prior_session["close"].iloc[-1])
    
    # 3. Current Day ETH Levels (04:00 to 09:29 ET)
    current_day = bars_2m[bars_2m.index.date == target_date]
    pm_bars = current_day.between_time("04:00", "09:29")
    rth_today = current_day.between_time("09:30", "15:59")
    
    pm_high = float(pm_bars["high"].max()) if not pm_bars.empty else None
    pm_low = float(pm_bars["low"].min()) if not pm_bars.empty else None
    rth_open = float(rth_today["open"].iloc[0]) if not rth_today.empty else None
    
    levels = DailyLevels(
        prior_high=prior_high,
        prior_close=prior_close,
        pm_high=pm_high,
        pm_low=pm_low,
        rth_open=rth_open
    )
    
    return levels, rth_vol_stats

def _safe_float(val) -> Optional[float]:
    """PHASE 1 FIX: Converts sentinels or nulls to None instead of crashing or coercing to 0.0"""
    if val is None or val == 'NaN': return None
    try: return float(val)
    except (ValueError, TypeError): return None

def _safe_int(val) -> Optional[int]:
    if val is None or val == 'NaN': return None
    try: return int(float(val))
    except (ValueError, TypeError): return None

async def get_valid_access_token() -> str:
    """Exchanges stored Refresh Token for a live 30-minute Access Token."""
    auth_string = f"{config.schwab_app_key}:{config.schwab_app_secret}"
    b64_auth = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": config.schwab_refresh_token
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.schwabapi.com/v1/oauth/token", headers=headers, data=payload)
        response.raise_for_status()
        return response.json().get("access_token")

async def get_price_history(ticker: str, access_token: str) -> Optional[pd.DataFrame]:
    """Fetches 10 days of 1-minute bars with extended hours data to ensure we capture 5 full trading days."""
    url = "https://api.schwabapi.com/marketdata/v1/pricehistory"
    params = {
        "symbol": ticker,
        "periodType": "day",
        "period": "10", 
        "frequencyType": "minute",
        "frequency": "1",
        "needExtendedHoursData": "true"
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            
        candles = data.get("candles", [])
        if not candles:
            return None
            
        df = pd.DataFrame(candles)
        # Schwab returns epoch milliseconds. Convert to US/Eastern timezone.
        df['datetime'] = pd.to_datetime(df['datetime'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('US/Eastern')
        df.set_index('datetime', inplace=True)
        return df

    except Exception as e:
        print(f"  [-] Failed to fetch Schwab price history for {ticker}: {e}")
        return None
    
async def get_live_market_data(ticker: str, access_token: str) -> Optional[OptionsChain]:
    """Fetches real-time options chains using null-safe parsing."""
    url = "https://api.schwabapi.com/marketdata/v1/chains"
    params = {
        "symbol": ticker,
        "contractType": "ALL",
        "range": "ALL",
        "fromDate": datetime.now().strftime("%Y-%m-%d"),
        "toDate": (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d")
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            
        underlying_price = data.get("underlyingPrice", 0.0)
        contracts = []

        for opt_type, map_key in [("call", "callExpDateMap"), ("put", "putExpDateMap")]:
            exp_date_map = data.get(map_key, {})
            
            for exp_date_str, strikes_map in exp_date_map.items():
                clean_date_str = exp_date_str.split(':')[0]
                exp_date = datetime.strptime(clean_date_str, "%Y-%m-%d").date()
                
                for strike_str, contract_list in strikes_map.items():
                    for c_data in contract_list:
                        contracts.append(OptionContract(
                            ticker=ticker,
                            strike=float(strike_str),
                            expiration=exp_date,
                            option_type=opt_type,
                            
                            # PHASE 1 FIX: Null-safe parsing for quotes and Greeks
                            bid=_safe_float(c_data.get('bid')),
                            ask=_safe_float(c_data.get('ask')),
                            last_price=_safe_float(c_data.get('last')),
                            volume=_safe_int(c_data.get('totalVolume')),
                            open_interest=_safe_int(c_data.get('openInterest')),
                            
                            implied_volatility=_safe_float(c_data.get('volatility')),
                            delta=_safe_float(c_data.get('delta')),
                            gamma=_safe_float(c_data.get('gamma')),
                            theta=_safe_float(c_data.get('theta')),
                            vega=_safe_float(c_data.get('vega'))
                        ))

        return OptionsChain(
            underlying={
                "price": underlying_price, 
                "ticker": ticker, 
                "timestamp": datetime.now(pytz.timezone('US/Eastern')).isoformat()
            },
            contracts=contracts
        )

    except Exception as e:
        print(f"  [-] Failed to fetch Schwab live chain for {ticker}: {e}")
        return None