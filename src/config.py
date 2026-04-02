"""
MaixCAM 人员入侵检测系统 - 全局配置常量
"""
# -*- coding: utf-8 -*-


# ===================== 模型配置 =====================
MODEL_PATH = "/root/models/yolo11n.mud"  # YOLO 官方模型 (YOLOv11n)
INPUT_SIZE = 832                         # 输入分辨率 
PERSON_CLASS_ID = 0                      # COCO: person = 0 (仅检测 person)
CONFIDENCE_THRESHOLD = 0.5               # 置信度阈值
IOU_THRESHOLD = 0.45                     # IOU 阈值

# ===================== ROI 配置 =====================
ROI_CENTER_W_RATIO = 0.5                 # 中心 ROI 宽度占比
ROI_CENTER_H_RATIO = 0.5                 # 中心 ROI 高度占比

# ===================== 双状态机配置 =====================
CENTER_ON_FRAMES = 5                     # center 连续检测到 person N 帧 -> on
CENTER_OFF_FRAMES = 10                    # center 连续未检测到 person M 帧 -> off
OUTER_ON_FRAMES = 5                      # outer 连续检测到 person N 帧 -> on
OUTER_OFF_FRAMES = 8                     # outer 连续未检测到 person M 帧 -> off

# ===================== 串口配置 =====================
UART_PORT = "/dev/ttyS1"
UART_BAUDRATE = 115200
UART_TX_PIN = "A19"
UART_RX_PIN = "A18"

# --- UART 优化部分 ---
# 预缓存常用包
MSG_ALARM_ON = b"<ALARM:1,D8>"  # ALARM:1 -> A(65)+L(76)+A(65)+R(82)+M(77)+:(58)+1(49) = 472 % 256 = 216 (D8)
MSG_ALARM_OFF = b"<ALARM:0,D7>" # ALARM:0 -> A(65)+L(76)+A(65)+R(82)+M(77)+:(58)+0(48) = 471 % 256 = 215 (D7)
MSG_HB = b"<HB,8A>"             # HB -> H(72)+B(66) = 138 % 256 = 138 (8A)
# 发送心跳包的时间间隔(秒)
HEARTBEAT_INTERVAL_S = 1.5 

# ===================== 云上报配置（MaixCam 直连） =====================
# 设备唯一标识，参与 MQTT topic 与图片上传参数
DEVICE_ID = "FORK-006"

# HTTP 图片上传配置
SERVER_BASE_URL = "http://192.168.50.129:5000"
UPLOAD_IMAGE_PATH = "/api/upload-image"
HTTP_TIMEOUT_S = 5

# MQTT 报警上报配置
MQTT_BROKER = "192.168.50.129"
MQTT_PORT = 1883
MQTT_TOPIC_TEMPLATE = "factory/forklift/{device_id}/alarm"

# 本地报警图片缓存目录与质量（质量参数在部分 MaixPy 版本可能被忽略）
ALARM_IMAGE_DIR = "/root/alarm_snapshots"
ALARM_IMAGE_QUALITY = 85

# ===================== 报警回溯图缓存配置 =====================
# 1 FPS 环形缓冲参数
SNAPSHOT_FPS = 1
RING_BUFFER_SIZE = 60
# 报警触发时回溯帧数（不含当前帧）：默认取 t-3,t-2,t-1,t 共 4 张
PRE_ALARM_FRAMES = 3

# 失败补传策略：仅内存队列，不跨重启持久化
UPLOAD_RETRY_INTERVAL_S = 5
UPLOAD_QUEUE_MAXLEN = 20
UPLOAD_RETRY_MAX = 5

# ===================== Debug 配置 =====================
DEBUG = False # True: 开启调试模式，输出额外的调试信息；False: 关闭调试模式，仅输出关键日志和事件
