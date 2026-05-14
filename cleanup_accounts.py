import requests
from auth_helper import get_bearer_token

# --- CONFIGURATION ---
MANAGEMENT_SERVER = "http://khangserver:9191"

def cleanup_failed_accounts():
    token = get_bearer_token()
    if not token:
        print("Authentication failed. Exiting.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 1. Fetch all M3U accounts
    print("Fetching M3U accounts...")
    accounts_resp = requests.get(f"{MANAGEMENT_SERVER}/api/m3u/accounts/", headers=headers)
    if accounts_resp.status_code != 200:
        print(f"Failed to fetch accounts: {accounts_resp.status_code}")
        return
    
    accounts_list = accounts_resp.json()

    # 2. Fetch all EPG sources to find matching names
    print("Fetching EPG sources...")
    epg_resp = requests.get(f"{MANAGEMENT_SERVER}/api/epg/epgdata/", headers=headers)
    epg_list = []
    if epg_resp.status_code == 200:
        epg_data = epg_resp.json()
        # Handle if epgs endpoint returns a dict or list
        epg_list = [v for k, v in epg_data.items() if k.isdigit()] if isinstance(epg_data, dict) else epg_data

    print(f"Found {len(accounts_list)} accounts. Scanning for errors...")

    for account in accounts_list:
        acc_id = account.get('id')
        acc_name = account.get('name')
        status = account.get('status', '').lower()

        # Check for anything that isn't 'success' (e.g., 'error', 'failed', etc.)
        if status == "error":
            print(f"\n[!] Cleanup Triggered: {acc_name} (ID: {acc_id}) | Status: {status}")

            # 3. Delete the M3U Account first
            print(f"  - Deleting M3U Account...")
            m3u_del_resp = requests.delete(f"{MANAGEMENT_SERVER}/api/m3u/accounts/{acc_id}/", headers=headers)
            
            if m3u_del_resp.status_code in [200, 204]:
                print(f"  - Success: M3U {acc_name} removed.")
                
                # 4. Find and delete the corresponding EPG (m3uName_EPG)
                target_epg_name = f"{acc_name}_EPG"
                for epg in epg_list:
                    if epg.get('name') == target_epg_name:
                        epg_id = epg.get('id')
                        print(f"  - Found matching EPG: {target_epg_name} (ID: {epg_id}). Deleting...")
                        epg_del_resp = requests.delete(f"{MANAGEMENT_SERVER}/api/epg/sources/{epg_id}/", headers=headers)
                        if epg_del_resp.status_code in [200, 204]:
                            print(f"  - Success: EPG removed.")
                        else:
                            print(f"  - Error: Could not remove EPG (Code: {epg_del_resp.status_code})")
            else:
                print(f"  - Error: Could not remove M3U (Code: {m3u_del_resp.status_code})")

    print("\nScan and cleanup finished.")

if __name__ == "__main__":
    cleanup_failed_accounts()