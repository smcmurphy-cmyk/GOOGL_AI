import asyncio
from curl_cffi.requests import AsyncSession
import yfinance as yf
from datetime import datetime, date
from models.market_data import UnderlyingQuote, OptionContract, OptionsChain

async def fetch_underlying(ticker: str) -> UnderlyingQuote:
    """
    Fetches the current underlying price with a weekend-safe historical fallback.
    """
    stock = yf.Ticker(ticker)
    price = 0.0
    
    try:
        info = stock.fast_info
        price = (
            getattr(info, "last_price", None)
            or getattr(info, "regular_market_price", None)
            or info.get("lastPrice")
            or 0.0
        )
    except Exception:
        pass

    # Fallback: Use the last close price if fast_info fails (critical for weekends)
    if not price or price <= 0:
        try:
            hist = stock.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        except Exception:
            pass

    return UnderlyingQuote(
        ticker=ticker,
        price=float(price or 0.0),
        timestamp=datetime.utcnow().isoformat()
    )

async def fetch_cboe_chain(ticker: str, max_retries: int = 3) -> dict:
    """
    Pulls the full options chain from CBOE's public delayed quotes endpoint.
    """
    ticker = ticker.upper().strip()
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.cboe.com/",
        "Origin": "https://www.cboe.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    for attempt in range(max_retries):
        try:
            async with AsyncSession(impersonate="chrome") as client:
                response = await client.get(
                    url,
                    headers=headers,
                    timeout=20.0,
                    allow_redirects=True,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[-] Final attempt failed for {ticker}. Error: {e}")
                raise
            print(f"[!] Attempt {attempt + 1} failed for {ticker} ({e}). Retrying in 2 seconds...")
            await asyncio.sleep(2)

async def get_market_data(ticker: str) -> OptionsChain:
    """
    Orchestrates ingestion with explicit error logging to debug the 0 contracts issue.
    """
    underlying = await fetch_underlying(ticker)
    raw_cboe_data = await fetch_cboe_chain(ticker)
    
    contracts = []
    
    data_block = raw_cboe_data.get('data', {})
    if data_block is None:
        data_block = {}
        
    options_data = data_block.get('options', [])
    
    if not options_data:
        print(f"\n[!] WARNING: CBOE returned empty options list for {ticker}. JSON Keys: {list(raw_cboe_data.keys())}")
        if 'error' in raw_cboe_data:
            print(f"    API Error Message: {raw_cboe_data['error']}")
            
    for item in options_data:
        option_symbol = item.get('option', '')
        
        try:
            if len(option_symbol) >= 15:
                # Parse Date
                date_part = option_symbol[-15:-9]
                exp_date = datetime.strptime(date_part, "%y%m%d").date()
                # Parse Call/Put
                is_call = option_symbol[-9] == 'C'
                # Parse Strike (last 8 digits divided by 1000)
                parsed_strike = float(option_symbol[-8:]) / 1000.0
            else:
                exp_str = item.get('expiration_date') or '2099-01-01'
                exp_date = date.fromisoformat(exp_str)
                is_call = 'C' in option_symbol
                parsed_strike = float(item.get('strike') or 0.0)

            contract = OptionContract(
                ticker=ticker,
                strike=parsed_strike,  # <-- Update this line to use parsed_strike
                expiration=exp_date,
                option_type="call" if is_call else "put",
                
                bid=float(item.get('bid') or 0.0),
                ask=float(item.get('ask') or 0.0),
                last_price=float(item.get('last_trade_price') or 0.0),
                volume=int(item.get('volume') or 0),
                open_interest=int(item.get('open_interest') or 0),
                
                implied_volatility=float(item.get('iv') or 0.0),
                delta=float(item.get('delta') or 0.0),
                gamma=float(item.get('gamma') or 0.0),
                theta=float(item.get('theta') or 0.0),
                vega=float(item.get('vega') or 0.0)
            )
            contracts.append(contract)
                      
        except Exception as e:
            print(f"\n[!] PARSING ERROR on {ticker}: {type(e).__name__} - {e}")
            print(f"[!] Raw JSON Item: {item}\n")
            break
            
    return OptionsChain(underlying=underlying, contracts=contracts)