from ultralytics import YOLO

# 加载模型（YOLO11n）
model = YOLO("yolo11n.pt")

# 推理
# results = model("https://ultralytics.com/images/bus.jpg")

# 保存结果
# results = model("https://ultralytics.com/images/bus.jpg", save = True)

# 置信度
results = model("https://ultralytics.com/images/bus.jpg", save = True, conf = 0.1)

