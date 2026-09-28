import json
import requests
import hashlib

EMAIL    = "axudoyberdiyev1989@gmail.com"
PASSWORD = "Aa8009988"  # eganing paroli

def md5(text):
    return hashlib.md5(text.encode()).hexdigest()

# Custom login
session = requests.Session()
session.headers.update({
    "clientType": "1",
    "customNo": "1000001",
    "clientVersion": "5.12.1.0517",
    "lang": "en_US",
    "featureCode": "1fc28fa018178a1cd1c091b13b2f9f02",
    "Content-Type": "application/x-www-form-urlencoded",
})

r = session.post(
    "https://apiisgp.ezvizlife.com/v3/users/login/v5",
    data={
        "account": EMAIL,
        "password": md5(PASSWORD),
        "featureCode": "1fc28fa018178a1cd1c091b13b2f9f02",
        "msgType": 0,
        "cuName": "SSmartPhone_Android",
    }
)
data = r.json()
session_id  = data["loginSession"]["sessionId"]
rf_session  = data["loginSession"]["rfSessionId"]

# pyezvizapi token formatida saqlash
token = {
    "session_id": session_id,
    "rf_session_id": rf_session,
    "username": EMAIL,
    "api_url": "apiisgp.ezvizlife.com",
}
with open("ezviz_token.json", "w") as f:
    json.dump(token, f)

print("✅ Token saqlandi!")
print(f"session_id: {session_id[:30]}...")