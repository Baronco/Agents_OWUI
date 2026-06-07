import os, requests, json
base = os.getenv('OWUI_BASE_URL','http://localhost:3000')
url = f"{base.rstrip('/')}/api/v1/auths/signup"
payload = {"name":"Test User","email":"testuser@example.com","password":"Pass123!","profile_image_url":"/user.png"}
resp = requests.post(url, json=payload)
print('status', resp.status_code)
print('body', resp.text)
