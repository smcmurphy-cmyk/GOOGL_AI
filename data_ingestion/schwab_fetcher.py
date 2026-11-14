import httpx
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from models.market_data import OptionsChain, OptionContract
from config.settings import config
import base64
import os

async def get_valid_access_token() -> str:
    """
    Exchanges your stored Refresh Token for a live 30-minute Access Token.
    """
    # FIX: Pull directly from the Pydantic config instead of os.getenv
    app_key = config.schwab_app_key
    app_secret = config.schwab_app_secret
    refresh_token = config.schwab_refresh_token
    
    auth_string = f"{app_key}:{app_secret}"
    b64_auth = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.schwabapi.com/v1/oauth/token", headers=headers, data=payload)
        response.raise_for_status()  # This will now pass successfully!
        return response.json().get("access_token")
    
async def get_live_market_data(
    ticker: str, 
    access_token: str
) -> Optional[OptionsChain]:
    """
    Fetches real-time options chains from the Schwab Developer API.
    Replaces the delayed CBOE feed.
    """
    url = "https://api.schwabapi.com/marketdata/v1/chains"
    
    # We want both calls and puts, targeting short-term expirations for scalping
    params = {
        "symbol": ticker,
        "contractType": "ALL",
        "range": "ALL",
        "fromDate": datetime.now().strftime("%Y-%m-%d"),
        "toDate": (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d") # Fetch up to 45 DTE
    }
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    try:
        # Use httpx for non-blocking async requests
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            
        underlying_price = data.get("underlyingPrice", 0.0)
        contracts = []

        # Schwab groups data into callExpDateMap and putExpDateMap
        for opt_type, map_key in [("call", "callExpDateMap"), ("put", "putExpDateMap")]:
            exp_date_map = data.get(map_key, {})
            
            # Iterate through expirations
            for exp_date_str, strikes_map in exp_date_map.items():
                # Schwab format: '2026-11-20:6' (Date : Days to Expiration)
                clean_date_str = exp_date_str.split(':')[0]
                exp_date = datetime.strptime(clean_date_str, "%Y-%m-%d").date()
                
                # Iterate through strikes
                for strike_str, contract_list in strikes_map.items():
                    # Usually a list of 1, but we iterate to be safe
                    for c_data in contract_list:
                        contracts.append(OptionContract(
                            ticker=ticker,
                            strike=float(strike_str),
                            expiration=exp_date,
                            option_type=opt_type,
                            
                            # Real-time bid/ask for accurate R-Multiple math
                            bid=float(c_data.get('bid', 0.0)),
                            ask=float(c_data.get('ask', 0.0)),
                            last_price=float(c_data.get('last', 0.0)),
                            volume=int(c_data.get('totalVolume', 0)),
                            open_interest=int(c_data.get('openInterest', 0)),
                            
                            implied_volatility=float(c_data.get('volatility', 0.0)),
                            delta=float(c_data.get('delta', 0.0)),
                            gamma=float(c_data.get('gamma', 0.0)),
                            theta=float(c_data.get('theta', 0.0)),
                            vega=float(c_data.get('vega', 0.0))
                        ))

        # FIX: De-indented to sit outside the 'for opt_type' loop
        return OptionsChain(
            underlying={
                "price": underlying_price, 
                "ticker": ticker, 
                "timestamp": datetime.now().isoformat()
            },
            contracts=contracts
        )

    except Exception as e:
        print(f"  [-] Failed to fetch Schwab live data for {ticker}: {e}")
        return None