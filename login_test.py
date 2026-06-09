import os, requests, json
base = os.getenv('OWUI_BASE_URL','http://localhost:3000')
login_url = f"{base.rstrip('/')}/api/v1/auths/login"
creds = {"email":"admin@example.com","password":"admin"}
resp = requests.post(login_url, json=creds)
print('login status', resp.status_code)
print('login body', resp.text)
