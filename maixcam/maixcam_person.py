# maixcam_person.py
# MaixCAM Pro + MaixPy 4 + YOLOv8n
# 功能：只检测 person，连续 N 帧判定，UART状态输出

import sys
from maix import camera, display, image, nn, uart

# ===================== 配置参数 =====================
CONTINUOUS_FRAME_THRESHOLD = 5      # 连续检测 N 帧才判定 DETECTED
MODEL_PATH = "/root/models/yolov8n.mud"
PERSON_CLASS_ID = 0                 # COCO: person = 0
CONFIDENCE_THRESHOLD = 0.5
IOU_THRESHOLD = 0.45
STATE_NOT_DETECTED = 0
STATE_DETECTED = 1

# ===================== 初始化 =====================
current_state = STATE_NOT_DETECTED
continuous_frames_count = 0

# UART
try:
    uart1 = uart.UART(port="/dev/ttyS2", baudrate=115200) 
except Exception as e:
    print("[Serial Error]", e)

# YOLOv8n 模型
try:
    yolo = nn.YOLOv8(model=MODEL_PATH, dual_buff=True)
    print(f"[OK] YOLOv8n loaded: {MODEL_PATH}")
except Exception as e:
    print("[FATAL] Load model failed:", e)
    sys.exit(1)

# 摄像头 & 屏幕
cam = camera.Camera(yolo.input_width(), yolo.input_height(), yolo.input_format())
# cam = camera.Camera(320, 240)
disp = display.Display()
print("[OK] Camera & Display ready")

print("[INFO] Starting person detection loop...")
# ===================== 主循环 =====================
while True:
    # 1. 采集原始图像
    img = cam.read()
    if img is None:
        continue

    # 2. 模型推理
    try:
        boxes = yolo.detect(img, conf_th=CONFIDENCE_THRESHOLD, iou_th=IOU_THRESHOLD)
    except Exception as e:
        print("[Inference Error]", e)
        boxes = []

    # 3. 检测 person
    person_detected = False
    for box in boxes:
        if box.class_id == PERSON_CLASS_ID:
            person_detected = True

            # 在显示图上画检测框
            img.draw_rect(box.x, box.y, box.w, box.h, color = image.COLOR_RED)
            break

    # 4. 状态机逻辑
    new_state = current_state
    if person_detected:
        continuous_frames_count += 1
        if continuous_frames_count >= CONTINUOUS_FRAME_THRESHOLD:
            new_state = STATE_DETECTED
    else:
        continuous_frames_count = 0
        new_state = STATE_NOT_DETECTED

    # 5. 状态变化才发 
    if new_state != current_state:
        if new_state == STATE_DETECTED:
            uart1.write(b'1')
            print("[STATE] DETECTED -> send 1")
        else:
            uart1.write(b'0')
            print("[STATE] NOT_DETECTED -> send 0")
        current_state = new_state

    # 6. 显示状态信息
    state_text = "DETECTED" if current_state else "NOT_DETECTED"
    count_text = f"{continuous_frames_count}/{CONTINUOUS_FRAME_THRESHOLD}"
    # color = (255, 0, 0) if current_state else (0, 255, 0)
    # img.draw_string(10, 10, state_text, color=color, scale=2)
    img.draw_string(10, 40, count_text, color = image.COLOR_RED, scale=1)

    # 7. 显示最终图像
    disp.show(img)
