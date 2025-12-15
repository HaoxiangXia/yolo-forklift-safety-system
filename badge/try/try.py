from ultralytics import YOLO
import cv2
import winsound
import time

model = YOLO("best.pt")
cap = cv2.VideoCapture(0)

# 设置分辨率（防止卡顿）
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

last_alarm_time = 0

while True:
    ret, frame = cap.read()
    if not ret:
        print("摄像头读取失败")
        break

    # YOLO检测
    results = model(frame, conf=0.5)

    detected = False

    # ✅ 逐个结果处理
    for r in results:
        if r.boxes is not None and len(r.boxes) > 0:
            detected = True

        # ✅ 关键：绘制检测框（YOLO自带）
        frame = r.plot()

    # ✅ 报警逻辑
    if detected:
        now = time.time()
        if now - last_alarm_time > 1:  # 1秒触发一次
            print("⚠️ 检测到目标！")
            winsound.Beep(1500, 500)
            last_alarm_time = now

    # ✅ 显示带检测框的画面
    cv2.imshow("YOLO Alarm", frame)

    if cv2.waitKey(1) == 27:  # ESC退出
        break

cap.release()
cv2.destroyAllWindows()
