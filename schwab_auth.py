import httpx
import base64
import urllib.parse

# --- INSERT YOUR KEYS HERE ---
APP_KEY ="7ooYc4a2aZHgJ1wWgJQ4oBg67sG7f08vpPG6aMlIGk3Kr5te"
APP_SECRET = "x4lBSpaEGCdFGYlD58iRwoffPoPQHr4iyVfXnrBgu2U2ZmFtARA6GfEefAGCzxXV"
REDIRECT_URI = "https://127.0.0.1"
# -----------------------------

def get_initial_tokens():
    # 1. Generate the login link
    auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?client_id={APP_KEY}&redirect_uri={REDIRECT_URI}"
    
    print("\n=== SCHWAB API AUTHENTICATION ===")
    print("1. Click this link and log in to your Schwab account:")
    print(f"\n{auth_url}\n")
    print("2. After approving the app, your browser will redirect to a broken page (127.0.0.1).")
    print("3. Copy the ENTIRE URL from your browser's address bar and paste it below.\n")
    
    redirected_url = input("Paste the full redirected URL here: ").strip()
    
    # 2. Extract the authorization code from the pasted URL
    try:
        parsed_url = urllib.parse.urlparse(redirected_url)
        code = urllib.parse.parse_qs(parsed_url.query)['code'][0]
        # Schwab requires the code to end with an '@' symbol, which browsers often URL-encode as '%40'
        if not code.endswith('@'):
            code += '@'
    except Exception as e:
        print("[-] Failed to parse the authorization code from the URL. Please try again.")
        return

    # 3. Exchange the code for a Refresh Token
    token_url = "https://api.schwabapi.com/v1/oauth/token"
    
    # Schwab requires Basic Auth encoding for the App Key and Secret
    auth_string = f"{APP_KEY}:{APP_SECRET}"
    b64_auth = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    print("\n[+] Exchanging code for tokens...")
    
    with httpx.Client() as client:
        response = client.post(token_url, headers=headers, data=payload)
        
        if response.status_code == 200:
            tokens = response.json()
            print("\n✅ SUCCESS! Save this Refresh Token to your .env file:\n")
            print(f"SCHWAB_REFRESH_TOKEN={tokens.get('refresh_token')}")
        else:
            print(f"\n[-] Authentication failed: {response.status_code}")
            print(response.text)

if __name__ == "__main__":
    get_initial_tokens()