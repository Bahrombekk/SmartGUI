import cv2

# Hikvision uchun stream path: /Streaming/Channels/101
# Dahua uchun: /cam/realmonitor?channel=1&subtype=0
# Kamera 1 RTSP porti: 8554
#url = "rtsp://admin:1q2w3e4r5t@89.236.216.206:8554/Streaming/Channels/101"
# Kamera 2 RTSP porti: 5544 (avval 5545 edi, o'zgargan). Parol: 1q2w3e4r5t.
url = "rtsp://admin:diyor1223 @89.236.216.206:5544/Streaming/Channels/101"
cam = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

if not cam.isOpened():
    print("Kameraga ulanib bo'lmadi. URL, login/parol yoki tarmoqni tekshiring.")
    raise SystemExit(1)

while True:
    ret, frame = cam.read()
    if not ret:
        print("Failed to grab frame")
        break
    cv2.imshow("Camera Feed", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam.release()
cv2.destroyAllWindows()
