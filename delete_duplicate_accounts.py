import requests
from collections import defaultdict
from urllib.parse import urlparse
from auth_helper import get_bearer_token

# --- CONFIGURATION ---
MANAGEMENT_SERVER = "http://khangserver:9191"
LIMIT_PER_HOST = 0

# CRITICAL: Keep this True first! Check the logs to see if it grabs the right hosts.
# Change to False ONLY when you see the correct hosts being targeted.
DRY_RUN = False 

def extract_host(item):
    """
    Attempts to find the host. Returns None if it can't find it 
    so we don't accidentally lump different hosts together.
    """
    # Check common keys for host or domain strings
    for key in ['host', 'domain', 'server', 'server_url']:
        if item.get(key):
            return str(item.get(key)).strip()
            
    # Check common keys for full URLs
    for key in ['url', 'uri', 'playlist_url', 'epg_url']:
        url = item.get(key)
        if url:
            try:
                netloc = urlparse(url).netloc
                if netloc:
                    return netloc
            except Exception:
                pass
                
    return None

def cleanup_duplicate_hosts():
    token = get_bearer_token()
    if not token:
        print("Authentication failed. Exiting.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    if DRY_RUN:
        print("====== RUNNING IN DRY-RUN MODE (NO DELETIONS WILL HAPPEN) ======")

    # 1. Fetch all M3U accounts
    print("\nFetching M3U accounts...")
    accounts_resp = requests.get(f"{MANAGEMENT_SERVER}/api/m3u/accounts/", headers=headers)
    if accounts_resp.status_code != 200:
        print(f"Failed to fetch accounts: {accounts_resp.status_code}")
        return
    accounts_list = accounts_resp.json()

    # 2. Fetch all EPG sources
    print("Fetching EPG sources...")
    epg_resp = requests.get(f"{MANAGEMENT_SERVER}/api/epg/sources/", headers=headers)
    epg_list = []
    if epg_resp.status_code == 200:
        epg_data = epg_resp.json()
        epg_list = [v for k, v in epg_data.items() if k.isdigit()] if isinstance(epg_data, dict) else epg_data
    else:
        print(f"Failed to fetch EPG sources: {epg_resp.status_code}")
        return

    # --- 3. Process M3U Accounts ---
    print(f"\nProcessing {len(accounts_list)} M3U accounts...")
    m3u_host_counts = defaultdict(int)
    
    for account in accounts_list:
        acc_id = account.get('id')
        acc_name = account.get('name')
        host = extract_host(account)

        if not host:
            print(f"[WARNING] Could not find host for M3U '{acc_name}' (ID: {acc_id}). Skiped to prevent accidental deletion.")
            print(f"          Available keys in data: {list(account.keys())}")
            continue

        m3u_host_counts[host] += 1

        if m3u_host_counts[host] > LIMIT_PER_HOST:
            if DRY_RUN:
                print(f"[DRY-RUN] Would delete excess M3U: {acc_name} | Host: {host} (Count: {m3u_host_counts[host]})")
            else:
                print(f"[!] Deleting excess M3U: {acc_name} | Host: {host}")
                m3u_del_resp = requests.delete(f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/", headers=headers)
                if m3u_del_resp.status_code not in [200, 204]:
                    print(f"  - Error removing M3U (Code: {m3u_del_resp.status_code})")
        else:
            print(f"[-] Keeping M3U: {acc_name} | Host: {host} ({m3u_host_counts[host]}/{LIMIT_PER_HOST})")

    # --- 4. Process EPG Sources ---
    print(f"\nProcessing {len(epg_list)} EPG sources...")
    epg_host_counts = defaultdict(int)
    
    for epg in epg_list:
        epg_id = epg.get('id')
        epg_name = epg.get('name')
        host = extract_host(epg)

        if not host:
            print(f"[WARNING] Could not find host for EPG '{epg_name}' (ID: {epg_id}). Skipped to prevent accidental deletion.")
            print(f"          Available keys in data: {list(epg.keys())}")
            continue

        epg_host_counts[host] += 1

        if epg_host_counts[host] > LIMIT_PER_HOST:
            if DRY_RUN:
                print(f"[DRY-RUN] Would delete excess EPG: {epg_name} | Host: {host} (Count: {epg_host_counts[host]})")
            else:
                print(f"[!] Deleting excess EPG: {epg_name} | Host: {host}")
                epg_del_resp = requests.delete(f"{MANAGEMENT_SERVER}/api/epg/sources/{epg_id}/", headers=headers)
                if epg_del_resp.status_code not in [200, 204]:
                    print(f"  - Error removing EPG (Code: {epg_del_resp.status_code})")
        else:
            print(f"[-] Keeping EPG: {epg_name} | Host: {host} ({epg_host_counts[host]}/{LIMIT_PER_HOST})")

    print("\nScan completed.")

if __name__ == "__main__":
    cleanup_duplicate_hosts()