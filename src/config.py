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

# ===================== Debug 配置 =====================
DEBUG = False # True: 开启调试模式，输出额外的调试信息；False: 关闭调试模式，仅输出关键日志和事件
