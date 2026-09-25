# iptv_utils.py
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

WHITELIST_FILE = "whitelist.txt"
BLACKLIST_FILE = "blacklist.txt"

def load_list_from_file(file_path):
    """Reads a text file line by line, cleans up whitespace, and ignores comments."""
    if not os.path.exists(file_path):
        print(f"Warning: File '{file_path}' not found. Proceeding with an empty list.")
        return []
    
    parsed_lines = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            clean_line = line.strip()
            if clean_line and not clean_line.startswith("#"):
                parsed_lines.append(clean_line)
    return parsed_lines

def get_robust_session(token):
    """Creates a requests session configured to handle flaky connections and large payloads."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Global headers for all calls using this session
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, deflate"  # Keeps heavy transfers lightweight
    })
    return session

def is_group_enabled(group_name, whitelist, blacklist, enable_all=False):
    """
    Evaluates group visibility using centralized rules:
    1. Blacklist takes absolute precedence.
    2. enable_all turns everything else on.
    3. Whitelist performs case-insensitive partial matching.
    """
    group_name_lower = group_name.lower()
    
    # 1. Blacklist check
    if any(bad_word.lower() in group_name_lower for bad_word in blacklist):
        return False
        
    # 2. Master override check
    if enable_all:
        return True
        
    # 3. Whitelist check
    return any(target.lower() in group_name_lower for target in whitelist)