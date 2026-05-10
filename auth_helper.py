import os
import requests
from dotenv import load_dotenv

load_dotenv()

def get_bearer_token():
    base_url = os.getenv("BASE_URL")
    username = os.getenv("DISP_USERNAME")
    password = os.getenv("DISP_PASSWORD")
    
    # Check if this is the correct login endpoint. 
    # Based on your log, this was the URL recorded.
    auth_url = f"{base_url}/api/accounts/token/" 
    print(username)
    print(password)
    payload = {
        "username": username,
        "password": password
    }
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:150.0) Gecko/20100101 Firefox/150.0"
    }

    try:
        # We use POST here because it's standard for sending credentials
        response = requests.post(auth_url, json=payload, headers=headers)
        
        # If POST fails with 405 (Method Not Allowed), fallback to GET
        if response.status_code == 405:
            response = requests.get(auth_url, json=payload, headers=headers)
            
        response.raise_for_status()
        data = response.json()
        
        # Check 'access' first, then 'refresh' 
        token = data.get("access") or data.get("refresh")
        return token

    except requests.exceptions.RequestException as e:
        print(f"Authentication failed: {e}")
        if response is not None:
            print(f"Server Response: {response.text}")
        return None