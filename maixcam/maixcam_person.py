import sys
import time
import os
from maix import camera, display, image, nn, uart, pinmap, err

# ===================== 配置参数与常量 =====================
# 1. 模型配置
MODEL_PATH = "/root/models/yolo11n.mud" # 模型
INPUT_SIZE = 832                      # 输入分辨率 imgsz
PERSON_CLASS_ID = 0                   # COCO: person = 0 (仅检测 person)
CONFIDENCE_THRESHOLD = 0.5            # 置信度阈值
IOU_THRESHOLD = 0.45                  # IOU 阈值

# 2. 状态机配置
ENTER_THRESHOLD = 5                 # 进入帧计数：连续 N 帧检测到 person → 进入入侵状态
EXIT_THRESHOLD = 8                  # 退出帧计数：连续 M 帧未检测到 person → 退出入侵状态
STATE_IDLE = 0                        # 状态：空闲/未入侵
STATE_INTRUSION = 1                   # 状态：入侵

# 3. 日志配置
LOG_DIR = "/root/logs"                # 日志存储目录

# ===================== 全局变量 =====================
current_state = STATE_IDLE
enter_frame_count = 0                 # 连续检测到人的帧计数
exit_frame_count = 0                  # 连续未检测到人的帧计数

# FPS 统计变量
total_frames = 0
start_time_s = time.time()          # 记录程序启动时间 (秒)
frame_times_s = []                  # 用于记录每帧结束时间，计算实时和平滑 FPS

# ===================== 日志系统函数 =====================
def write_run_log():
    """
    功能：统计并记录程序运行日志到文件 (/root/logs/run_xxx.log)
    记录内容：总运行帧数、总运行时间、平均FPS、最大FPS、最小FPS。
    """
    global total_frames, start_time_s, frame_times_s
    
    # 每次程序启动记录一次运行日志，如果没有任何帧数据则跳过
    if total_frames == 0:
        print("[Log] No frames processed, skipping log file creation.")
        return

    # 1. 计算统计数据
    end_time_s = time.time()
    # 总运行时间 (秒)
    total_run_time_s = end_time_s - start_time_s
    
    # 平均 FPS
    avg_fps = total_frames / total_run_time_s if total_run_time_s > 0 else 0
    
    # 计算最大/最小 FPS (需要至少两帧数据)
    max_fps = 0.0
    min_fps = 0.0
    
    if len(frame_times_s) > 1:
        # 转换为实际帧间隔时间（单位：秒）
        # 使用 time.time() 返回秒，因此直接相减得到时间间隔
        frame_intervals_s = [frame_times_s[i] - frame_times_s[i-1] for i in range(1, len(frame_times_s))]
        
        # 最小帧间隔时间 (对应最大 FPS)
        min_interval = min(frame_intervals_s) if frame_intervals_s else 0
        max_fps = 1.0 / min_interval if min_interval > 0 else 0
        
        # 最大帧间隔时间 (对应最小 FPS)
        max_interval = max(frame_intervals_s) if frame_intervals_s else 0
        min_fps = 1.0 / max_interval if max_interval > 0 else 0
    
    # 2. 格式化日志内容 (结构清晰)
    log_content = f"""
==================== MaixCAM 运行日志 ====================
程序启动时间 (Unix): {start_time_s:.4f} 秒
程序退出时间 (Unix): {end_time_s:.4f} 秒
----------------------------------------------------------
总运行帧数: {total_frames}
总运行时间: {total_run_time_s:.2f} 秒
----------------------------------------------------------
平均 FPS (总): {avg_fps:.2f}
最大 FPS (峰值): {max_fps:.2f}
最小 FPS (谷值): {min_fps:.2f}
----------------------------------------------------------
状态机配置:
    进入阈值 N: {ENTER_THRESHOLD}
    退出阈值 M: {EXIT_THRESHOLD}
==========================================================
"""
    
    # 3. 写入文件
    try:
        # 尝试创建日志目录
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        
        # 使用当前时间戳命名日志文件
        timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())
        log_file_path = os.path.join(LOG_DIR, f"run_{timestamp}.log")
        
        with open(log_file_path, 'w') as f:
            f.write(log_content)
        
        print(f"[Log] 运行日志已保存至: {log_file_path}")
    except Exception as e:
        print(f"[FATAL] 写入日志失败，请检查文件系统权限: {e}")

# ===================== 初始化 =====================
print("[INFO] 开始初始化 MaixCAM 系统...")

# 1. 串口初始化 (用于状态输出)
# 使用 /dev/ttyS1
uart1 = None
try:
    # 串口引脚配置 (A19:TX, A18:RX)
    pin_function = {
        "A19": "UART1_TX",
        "A18": "UART1_RX",
    }
    for pin, func in pin_function.items():
        err.check_raise(pinmap.set_pin_function(pin, func), f"Failed set pin {pin} function to {func}")
    uart1 = uart.UART(port="/dev/ttyS1", baudrate=115200)
    print("[OK] UART1 115200 ready for state output")
except Exception as e:
    print(f"[Serial Error] UART初始化失败，不影响主流程: {e}")


# 2. 模型加载
yolo = None
try:
    # 加载模型，使用双缓冲区以提高性能
    yolo = nn.YOLO11(model=MODEL_PATH, dual_buff=True)
    # 检查模型输入尺寸
    if yolo.input_width() != INPUT_SIZE or yolo.input_height() != INPUT_SIZE:
        print(f"[WARN] 模型输入尺寸({yolo.input_width()}x{yolo.input_height()})与预设({INPUT_SIZE}x{INPUT_SIZE})不匹配！请检查模型配置。")
    print(f"[OK] YOLOv11n 模型加载成功: {MODEL_PATH}")
except Exception as e:
    print(f"[FATAL] 加载模型失败: {e}")
    sys.exit(1)

# 3. 摄像头 & 屏幕初始化
cam = None
disp = None
try:
    # 摄像头采集分辨率需与模型输入匹配 (832x832)
    cam = camera.Camera(yolo.input_width(), yolo.input_height(), yolo.input_format())
    disp = display.Display()
    print("[OK] 摄像头 & 屏幕初始化成功")
except Exception as e:
    print(f"[FATAL] 摄像头/屏幕初始化失败: {e}")
    if yolo: yolo.deinit()
    sys.exit(1)


# ===================== 主循环 =====================
print("[INFO] 启动人员检测主循环...")

try:
    # 记录程序启动时间（用于总运行时间计算）
    # start_time_ms = time.ticks_ms()
    # start_time_ms 已在全局变量中初始化

    while True:
        # 帧开始时间，用于 FPS 统计
        frame_start_s = time.time()

        # 1. 采集原始图像
        # 相机采集与模型输入需匹配 (832x832)
        img = cam.read()
        if img is None:
            continue
        
        # 2. 模型推理
        boxes = []
        try:
            boxes = yolo.detect(img, conf_th=CONFIDENCE_THRESHOLD, iou_th=IOU_THRESHOLD)
        except Exception as e:
            print(f"[Inference Error] 推理失败: {e}")
        
        # 3. 筛选 person 类别并绘制
        person_detected = False
        person_boxes = []
        for box in boxes:
            # 仅检测 person 一个类别
            if box.class_id == PERSON_CLASS_ID:
                person_detected = True
                person_boxes.append(box)
                
                # 在画面中清晰标注
                img.draw_rect(box.x, box.y, box.w, box.h, color=image.COLOR_RED, thickness=2)
                
        # 4. 状态机逻辑：使用“进入/退出”双计数
        # 连续 N 帧检测到 person → 进入入侵状态 (state = 1)
        # 连续 M 帧未检测到 person → 退出入侵状态 (state = 0)
        new_state = current_state

        if person_detected:
            # 检测到人: 增加进入计数, 重置退出计数
            enter_frame_count += 1
            exit_frame_count = 0

            # 只有在 Idle 状态下，达到 N 阈值才切换到 Intrusion
            if current_state == STATE_IDLE and enter_frame_count >= ENTER_THRESHOLD:
                new_state = STATE_INTRUSION
                
        else:
            # 未检测到人: 增加退出计数, 重置进入计数
            enter_frame_count = 0
            exit_frame_count += 1

            # 只有在 Intrusion 状态下，达到 M 阈值才切换到 Idle
            if current_state == STATE_INTRUSION and exit_frame_count >= EXIT_THRESHOLD:
                new_state = STATE_IDLE

        # 5. 状态切换与输出 (仅在状态发生切换时触发输出，例如串口输出或日志输出)
        if new_state != current_state:
            current_state = new_state
            
            log_output = ""
            uart_data = b''

            if current_state == STATE_INTRUSION:
                log_output = "INTRUSION: Person Detected" # 日志输出
                uart_data = b'1'                         # 串口输出 '1'
            else:
                log_output = "IDLE: Person Cleared"      # 日志输出
                uart_data = b'0'                         # 串口输出 '0'
            
            print(f"[STATE CHANGE] {log_output}")
            if uart1:
                uart1.write(uart_data)
                
        # 6. 统计信息计算与显示
        
        # 记录帧结束时间，用于 FPS 统计
        frame_end_s = time.time()
        frame_times_s.append(frame_end_s)
        total_frames += 1
        
        # 保持最近 10 帧时间戳，用于计算平滑 FPS
        if len(frame_times_s) > 10:
            frame_times_s.pop(0)

        # 实时 FPS 计算
        fps = 0.0
        if len(frame_times_s) > 1:
            # 直接计算时间差 (秒)
            time_diff_s = frame_times_s[-1] - frame_times_s[0]
            if time_diff_s > 0:
                # FPS = (帧数 - 1) / 总时间 (秒)
                fps = (len(frame_times_s) - 1) / time_diff_s
        
        # 状态显示文本
        status_text = "Intrusion" if current_state == STATE_INTRUSION else "Idle"
        state_color = image.COLOR_RED if current_state == STATE_INTRUSION else image.COLOR_GREEN
        
        # 实时检测帧计数显示
        if current_state == STATE_INTRUSION:
            # 显示进入计数 / N (N=5)
            count_info = f"IN: {enter_frame_count}/{ENTER_THRESHOLD}"
        else:
            # 显示退出计数 / M (M=8)
            count_info = f"OUT: {exit_frame_count}/{EXIT_THRESHOLD}"
        
        # 绘制到图像上 (清晰标注)
        img.draw_string(10, 10, f"Status: {status_text}", color=state_color, scale=2)      # 当前状态
        img.draw_string(10, 50, f"FPS: {fps:.2f}", color=image.COLOR_YELLOW, scale=2)      # 实时 FPS 计数
        img.draw_string(10, 90, f"Count: {count_info}", color=image.COLOR_WHITE, scale=2) # 当前进入计数 / 退出计数

        # 7. 显示最终图像
        disp.show(img)

except KeyboardInterrupt:
    print("[INFO] 程序被用户中断...")
except Exception as e:
    print(f"[FATAL] 主循环发生意外错误: {e}")

finally:
    # 8. 程序退出时记录运行日志
    print("[INFO] 正在记录运行日志...")
    write_run_log()
    print("[INFO] 释放资源并退出。")
    # 资源释放
    if uart1:
        uart1.close()
    if yolo:
        yolo.deinit()
    if cam:
        cam.close()
    if disp:
        disp.close()
    sys.exit(0)
