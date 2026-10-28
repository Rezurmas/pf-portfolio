"""Przywraca listę wyróżnionych zdjęć (snapshot użytkownika) przez API."""
import json

import httpx

BASE = "http://127.0.0.1:8000"
IDS = [1, 2, 17, 19, 20, 4, 5, 10, 22, 23]

with httpx.Client() as c:
    r = c.post(BASE + "/api/login", json={"password": "Dawidek200909"})
    print("login:", r.status_code)
    me = c.get(BASE + "/api/me").json()
    csrf = me.get("csrf", "")
    r = c.post(
        BASE + "/api/admin/featured",
        json={"ids": IDS, "sizes": {}},
        headers={"X-CSRF": csrf},
    )
    print("restore:", r.status_code)
    site = c.get(BASE + "/api/site").json()
    print("featured po przywróceniu:", len(site["featured"]))
