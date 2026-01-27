"""
MaixCAM 人员入侵检测系统 - 全局配置常量
"""

# ===================== 模型配置 =====================
MODEL_PATH = "/root/models/yolo11n.mud"  # YOLO 官方模型 (YOLOv11n)
INPUT_SIZE = 832                         # 输入分辨率 imgsz 设置为 832
PERSON_CLASS_ID = 0                      # COCO: person = 0 (仅检测 person)
CONFIDENCE_THRESHOLD = 0.5               # 置信度阈值
IOU_THRESHOLD = 0.45                     # IOU 阈值

# ===================== 状态机配置 =====================
ENTER_THRESHOLD_N = 5                    # 进入帧计数 N=5：连续 N 帧检测到 person → 进入入侵状态
EXIT_THRESHOLD_M = 8                     # 退出帧计数 M=8：连续 M 帧未检测到 person → 退出入侵状态
STATE_IDLE = 0                           # 状态：空闲/未入侵
STATE_INTRUSION = 1                      # 状态：入侵

# ===================== 串口配置 =====================
UART_PORT = "/dev/ttyS1"
UART_BAUDRATE = 115200
UART_TX_PIN = "A19"
UART_RX_PIN = "A18"