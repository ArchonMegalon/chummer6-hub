#!/usr/bin/env python3
"""Check support/contact case flow on live chummer.run."""
import sys
import requests

BASE_URL = "https://chummer.run"
ROUTES = ["/contact", "/help", "/faq", "/home/access", "/account/support"]

def main():
    all_ok = True
    for route in ROUTES:
        try:
            resp = requests.get(BASE_URL + route, timeout=10, allow_redirects=True)
            if resp.status_code in (200, 302):
                print(f"{route} ok ({resp.status_code})")
            else:
                print(f"{route} fail ({resp.status_code})")
                all_ok = False
        except Exception as e:
            print(f"{route} error: {e}")
            all_ok = False
    if all_ok:
        print("All routes ok")
    else:
        print("Some routes failed")
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
