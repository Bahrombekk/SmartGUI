import requests
import hashlib
import json

def md5(text):
    return hashlib.md5(text.encode()).hexdigest()

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
        "account": "axudoyberdiyev1989@gmail.com",
        "password": md5("Aa8009988"),
        "featureCode": "1fc28fa018178a1cd1c091b13b2f9f02",
        "msgType": 0,
        "cuName": "SSmartPhone_Android",
    }
)
data = r.json()
session_id = data["loginSession"]["sessionId"]
rf_session_id = data["loginSession"]["rfSessionId"]
api_url = data["loginArea"]["apiDomain"]
session.headers.update({"sessionId": session_id})
print("✅ Login!")

# MFA kod yuborish
r2 = session.post(
    f"https://{api_url}/v3/dps/appSendVerCode",
    data={
        "account": "axudoyberdiyev1989@gmail.com",
        "bizType": "TERMINAL_BIND",
        "from": "axudoyberdiyev1989@gmail.com",
    }
)
print(f"MFA yuborish: {r2.text}")

mfa_code = input("📧 Emaildan kelgan kodni kiriting: ")

# Kodni tasdiqlash va cam_key olish
r3 = session.post(
    f"https://{api_url}/v3/userdevices/v1/cameras/encryptkey",
    data={
        "deviceSerial": "GK8973616",
        "channelNo": 1,
        "validateCode": mfa_code,
    }
)
print(f"cam_key: {r3.text}")

# Token faylini yangilash
token = {
    "session_id": session_id,
    "rf_session_id": rf_session_id,
    "username": "axudoyberdiyev1989@gmail.com",
    "api_url": api_url,
}
with open("ezviz_token.json", "w") as f:
    json.dump(token, f)
print("✅ Token yangilandi!")