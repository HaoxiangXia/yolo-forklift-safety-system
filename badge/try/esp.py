from ultralytics import YOLO
import cv2
import serial
import time

model = YOLO("best.pt")
cap = cv2.VideoCapture(0)

ser = serial.Serial('COM7', 115200, timeout=0.1)

alarm_on = False

while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame, conf=0.5)

    detected = False

    for r in results:
        if r.boxes is not None and len(r.boxes) > 0:
            detected = True
        frame = r.plot()

    # ✅ 状态变化才发串口（防抖）
    if detected and not alarm_on:
        ser.write(b'1')
        alarm_on = True
        print("➡️ ESP32 D2 = HIGH")

    elif not detected and alarm_on:
        ser.write(b'0')
        alarm_on = False
        print("⬅️ ESP32 D2 = LOW")

    cv2.imshow("YOLO + ESP32", frame)
    if cv2.waitKey(1) == 27:
        break

cap.release()
ser.close()
cv2.destroyAllWindows()
