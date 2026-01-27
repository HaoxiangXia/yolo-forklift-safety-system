"""
MaixCAM 人员入侵检测系统 - 主程序
整合 camera, display, detector, logic, logger 模块，运行主循环
"""

import sys
import time
from maix import camera, display, image, uart, pinmap, err
import config
from detector import Detector
from logic import StateMachine
from logger import RunLogger

def on_state_change(new_state, is_rollback):
    """
    状态机切换回调函数。
    Args:
        new_state (int): 新状态（STATE_IDLE 或 STATE_INTRUSION）。
        is_rollback (bool): 是否为误触发回滚。
    """
    if new_state == config.STATE_INTRUSION:
        log_output = "INTRUSION: Person Detected"
        uart_data = b'1'
        logger.record_state_change("INTRUSION_ENTER", is_rollback)
    else:
        log_output = "IDLE: Person Cleared"
        uart_data = b'0'
        logger.record_state_change("IDLE_EXIT", is_rollback)
    
    print(f"[STATE CHANGE] {log_output}")
    if uart1:
        uart1.write(uart_data)

# ===================== 初始化 =====================
print("[INFO] 开始初始化 MaixCAM 系统...")

# 1. 串口初始化 (用于状态输出)
uart1 = None
try:
    pin_function = {
        config.UART_TX_PIN: "UART1_TX",
        config.UART_RX_PIN: "UART1_RX",
    }
    for pin, func in pin_function.items():
        err.check_raise(pinmap.set_pin_function(pin, func), f"Failed set pin {pin} function to {func}")
    uart1 = uart.UART(port=config.UART_PORT, baudrate=config.UART_BAUDRATE)
    print("[OK] UART1 115200 ready for state output")
except Exception as e:
    print(f"[Serial Error] UART初始化失败，不影响主流程: {e}")

# 2. 初始化检测器
detector = Detector()

# 3. 初始化状态机
state_machine = StateMachine(on_state_change=on_state_change)

# 4. 初始化摄像头 & 屏幕
cam = None
disp = None
try:
    # 如果 input_format 为 None，则使用默认格式
    if detector.input_format is None:
        cam = camera.Camera(detector.input_width, detector.input_height)
    else:
        cam = camera.Camera(detector.input_width, detector.input_height, detector.input_format)
    disp = display.Display()
    print("[OK] 摄像头 & 屏幕初始化成功")
except Exception as e:
    print(f"[FATAL] 摄像头/屏幕初始化失败: {e}")
    detector.deinit()
    sys.exit(1)

# 5. 初始化日志模块
logger = RunLogger(
    model_name="YOLOv11n",
    input_res=config.INPUT_SIZE,
    enter_N=config.ENTER_THRESHOLD_N,
    exit_M=config.EXIT_THRESHOLD_M
)
print("[OK] 日志模块初始化成功")

# ===================== 主循环 =====================
print("[INFO] 启动人员检测主循环...")

try:
    while True:
        # 帧开始时间，用于 FPS 统计
        frame_start_s = time.time()

        # 1. 采集原始图像
        cam_start_s = time.time()
        img = cam.read()
        cam_end_s = time.time()
        cam_time_s = cam_end_s - cam_start_s
        
        if img is None:
            continue
        
        # 2. 模型推理
        nn_start_s = time.time()
        person_boxes = detector.predict(img)
        nn_end_s = time.time()
        nn_time_s = nn_end_s - nn_start_s
        
        # 3. 绘制检测框
        for box in person_boxes:
            img.draw_rect(box.x, box.y, box.w, box.h, color=image.COLOR_RED, thickness=2)
        
        # 4. 状态机逻辑判定
        person_detected = len(person_boxes) > 0
        state_changed = state_machine.update(person_detected)
        
        # 5. 绘制 UI 信息
        disp_start_s = time.time()
        
        # 获取当前状态和计数
        current_state = state_machine.get_state()
        enter_count, exit_count = state_machine.get_counts()
        
        # 状态显示文本
        status_text = "Intrusion" if current_state == config.STATE_INTRUSION else "Idle"
        state_color = image.COLOR_RED if current_state == config.STATE_INTRUSION else image.COLOR_GREEN
        
        # 实时检测帧计数显示
        if current_state == config.STATE_INTRUSION:
            count_info = f"IN: {enter_count}/{config.ENTER_THRESHOLD_N}"
        else:
            count_info = f"OUT: {exit_count}/{config.EXIT_THRESHOLD_M}"
        
        # 绘制到图像上 (清晰标注)
        img.draw_string(10, 10, f"Status: {status_text}", color=state_color, scale=2)      # 当前状态
        img.draw_string(10, 50, f"Count: {count_info}", color=image.COLOR_WHITE, scale=2) # 当前进入计数 / 退出计数

        # 6. 显示最终图像
        disp.show(img)
        disp_end_s = time.time()
        disp_time_s = disp_end_s - disp_start_s
        
        # 7. 记录本帧耗时到日志模块
        other_time_s = (time.time() - frame_start_s) - (cam_time_s + nn_time_s + disp_time_s)
        if other_time_s < 0:
            other_time_s = 0.0
        logger.record_frame(time_cam=cam_time_s, time_nn=nn_time_s, time_disp=disp_time_s, time_other=other_time_s)

except KeyboardInterrupt:
    print("[INFO] 程序被用户中断...")
except Exception as e:
    print(f"[FATAL] 主循环发生意外错误: {e}")

finally:
    # 8. 程序退出时记录运行日志
    print("[INFO] 正在记录运行日志...")
    logger.write_log()
    print("[INFO] 释放资源并退出。")
    # 资源释放
    if uart1:
        uart1.close()
    detector.deinit()
    if cam:
        cam.close()
    if disp:
        disp.close()
    sys.exit(0)