import cv2
from ultralytics import YOLO

# 1. 加载 YOLO 官方模型（可换 yolov8n.pt / yolo11n.pt 等）
model = YOLO("yolo11n.pt")  # n 最快，适合实时

# 2. 打开 USB 摄像头
cap = cv2.VideoCapture(0)  # 0 = 默认USB摄像头

if not cap.isOpened():
    print("无法打开摄像头")
    exit()

# 3. 推理循环
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # 4. YOLO 推理（只检测 person）
    results = model(
        frame,
        conf=0.4,          # 置信度阈值
        classes=[0],       # 只检测 person
        device=0           # GPU:0  CPU:-1
    )

    # 5. 绘制结果
    annotated_frame = results[0].plot()

    # 6. 显示
    cv2.imshow("Person Detection", annotated_frame)

    # 按 q 退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 7. 释放资源
cap.release()
cv2.destroyAllWindows()
