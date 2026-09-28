from pyezviz import EzvizClient

# === KAMERA EGASINING HISOBI ===
EMAIL    = "axudoyberdiyev1989@gmail.com"
PASSWORD = "Aa8009988"  # eganing paroli
REGION   = "apiisgp.ezvizlife.com"

print("🔐 Eganing hisobi bilan login qilinmoqda...")
client = EzvizClient(EMAIL, PASSWORD, REGION)
client.login()
print("✅ Login muvaffaqiyatli!\n")

services  = client.get_service_urls()
vtm_addr  = services.get("vtmAddr", "")
vtm_port  = services.get("vtmPort", 8554)

devices = client.get_device_infos()
online  = [(s, d) for s, d in devices.items() if d.get("deviceInfos", {}).get("status") == 1]

print(f"📷 Jami: {len(devices)} ta kamera | 🟢 Online: {len(online)} ta\n")
print("=" * 60)

results = []

for serial, data in devices.items():
    info   = data.get("deviceInfos", {})
    name   = info.get("name", serial)
    status = info.get("status", 0)
    model  = info.get("deviceType", "")
    wifi   = data.get("WIFI", {})
    signal = wifi.get("signal", "?")
    net    = wifi.get("netType", "")

    print(f"📌 {name}")
    print(f"   Serial : {serial}")
    print(f"   Model  : {model}")
    print(f"   Tarmoq : {net} | Signal: {signal}%")
    print(f"   Status : {'🟢 Online' if status == 1 else '🔴 Offline'}")

    if status != 1:
        print()
        results.append({"name": name, "serial": serial, "status": "offline"})
        continue

    # cam_key olish
    cam_key = None
    try:
        cam_key = client.get_cam_key(serial)
        print(f"   🔑 cam_key: {cam_key}")
    except Exception as e:
        print(f"   ⚠️  cam_key xato: {e}")

    # RTSP URL yasash
    if cam_key:
        rtsp = f"rtsp://{serial}:{cam_key}@{vtm_addr}:{vtm_port}/EzvizStream"
    else:
        rtsp = f"rtsp://{serial}:{serial}@{vtm_addr}:{vtm_port}/EzvizStream"
    
    print(f"   🎥 RTSP: {rtsp}")
    print()
    
    results.append({
        "name": name,
        "serial": serial,
        "status": "online",
        "cam_key": cam_key,
        "rtsp": rtsp
    })

print("=" * 60)
print("\n✅ Online kameralar RTSP URL lari:\n")
for r in results:
    if r["status"] == "online":
        print(f"  {r['name']}")
        print(f"  {r['rtsp']}\n")

print("💡 VLC > Media > Open Network Stream ga RTSP URL ni joylashtiring")