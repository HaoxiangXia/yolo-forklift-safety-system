"""
YOLO + ESP32 报警系统（工程级最终版）

功能：
- 使用笔记本摄像头实时检测
- 显示检测框
- 连续多帧检测才触发报警
- 串口发送 1 / 0 控制 ESP32
"""

# ======== 基础库 ========
import cv2                    # 摄像头 & 画面显示
import time                   # 时间控制
import serial                 # 串口通信
from ultralytics import YOLO  # YOLO 模型

# ======== 用户配置区（最重要） ========

MODEL_PATH = "best.pt"        # 训练好的模型
CAMERA_ID = 0                 # 0 = 笔记本内置摄像头
SERIAL_PORT = "COM10"          # 改成 ESP32 的端口⚠️ ⚠️ ⚠️ 
BAUD_RATE = 115200

CONF_THRES = 0.5              # YOLO 置信度阈值
TRIGGER_FRAMES = 1            # 连续多少帧检测到才算“真的检测到”

# 每隔多少帧跑一次 YOLO（降低算力消耗）
DETECT_INTERVAL = 2

# 摄像头分辨率（越低越快）
FRAME_WIDTH = 1280   #640
FRAME_HEIGHT = 720   #480

# =====================================

def main():
    # ======== 1. 初始化模型 ========
    print("[INFO] 加载 YOLO 模型...")
    model = YOLO(MODEL_PATH)

    # ======== 2. 打开摄像头 ========
    print("[INFO] 打开摄像头...")
    cap = cv2.VideoCapture(CAMERA_ID)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        print("[ERROR] 摄像头打开失败")
        return

    # ======== 3. 打开串口 ========
    print("[INFO] 打开串口:", SERIAL_PORT)
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1)
    except Exception as e:
        print("[ERROR] 串口打开失败:", e)
        return

    # ======== 4. 状态变量 ========

    frame_count = 0            # 总帧计数
    detect_count = 0           # 连续检测到的帧数

    alarm_state = False        # 当前报警状态（是否已触发）
    last_alarm_state = False   # 上一次报警状态（用于比较）

    # ======== 5. 主循环 ========
    print("[INFO] 开始检测，按 ESC 退出")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] 读取摄像头失败")
            break

        frame_count += 1
        detected_this_frame = False

        # ======== 5.1 降频检测 ========
        # 不是每一帧都跑 YOLO
        if frame_count % DETECT_INTERVAL == 0:
            results = model(frame, conf=CONF_THRES, verbose=False) # verbose控制Ultralytics YOLO的默认日志输出

            # 处理 YOLO 输出
            for r in results:
                # 如果检测框数量 > 0，说明检测到目标
                if r.boxes is not None and len(r.boxes) > 0:
                    detected_this_frame = True

                # 使用 YOLO 自带方法画框
                frame = r.plot()

        # ======== 5.2 连续帧稳定判定 ========
        if detected_this_frame:
            detect_count += 1
        else:
            detect_count = 0

        # 只有连续 N 帧检测到，才认为“真的检测到”
        if detect_count >= TRIGGER_FRAMES:
            alarm_state = True
        else:
            alarm_state = False

        # ======== 5.3 状态变化才通知 ESP32 ========
        if alarm_state != last_alarm_state:
            try:
                if alarm_state:
                    ser.write(b'1')   # 触发 ESP32
                    print("[ALARM] ON → 发送 '1'")
                else:
                    ser.write(b'0')   # 释放 ESP32
                    print("[ALARM] OFF → 发送 '0'")
            except Exception as e:
                print("[ERROR] 串口发送失败:", e)

            last_alarm_state = alarm_state

        # ======== 5.4 显示画面 ========
        cv2.imshow("YOLO Alarm System", frame)

        # ESC 键退出
        if cv2.waitKey(1) == 27:
            break

    # ======== 6. 资源释放 ========
    cap.release()
    ser.close()
    cv2.destroyAllWindows()
    print("[INFO] 程序已退出")

# ======== 程序入口 ========
if __name__ == "__main__":
    main()
