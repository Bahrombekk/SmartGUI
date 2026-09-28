import cv2

SERIAL = "GK8973616"
URL    = f"http://localhost:8558/{SERIAL}.ts"

cap = cv2.VideoCapture(URL, cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 30000)
cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000)

print("🎥 Ulanish...")
if not cap.isOpened():
    print("❌ Ulanmadi")
else:
    print("✅ Ulandi! Oyna ochilmoqda...")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Frame kelmadi, qayta urinilmoqda...")
            cap.open(URL)
            continue
        cv2.imshow(f"🎥 {SERIAL}", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()