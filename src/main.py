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
from logger import RunLogger, debug_print # 导入debug_print

def on_state_change(new_state, is_rollback, prev_state=None, enter_count=None, exit_count=None):
    """
    状态机切换回调函数。
    Args:
        new_state (int): 新状态（STATE_IDLE 或 STATE_INTRUSION）。
        is_rollback (bool): 是否为误触发回滚。
        prev_state (int): 前一状态
        enter_count (int): 进入计数
        exit_count (int): 退出计数
    """
    if new_state == config.STATE_INTRUSION:
        log_output = "INTRUSION: Person Detected"
        uart_data = b'1'
        logger.record_state_change("INTRUSION_ENTER", is_rollback)
        # 记录事件日志
        logger.log_state_change(
            prev_state=prev_state if prev_state is not None else config.STATE_IDLE,
            new_state=new_state,
            trigger_reason=f"enter_count>={config.ENTER_THRESHOLD_N}",
            person_count=1,  # 进入入侵状态说明检测到人
            state_counter=enter_count if enter_count is not None else 0,
            extra="rollback" if is_rollback else ""
        )
    else:
        log_output = "IDLE: Person Cleared"
        uart_data = b'0'
        logger.record_state_change("IDLE_EXIT", is_rollback)
        # 记录事件日志
        logger.log_state_change(
            prev_state=prev_state if prev_state is not None else config.STATE_INTRUSION,
            new_state=new_state,
            trigger_reason=f"exit_count>={config.EXIT_THRESHOLD_M}",
            person_count=0,  # 退出入侵状态说明未检测到人
            state_counter=exit_count if exit_count is not None else 0,
            extra="rollback" if is_rollback else ""
        )
    
    print(f"[STATE CHANGE] {log_output}")
    if uart1:
        try:
            uart1.write(uart_data)
        except Exception as e:
            logger.log_error("uart", "uart_write_failed", extra=f"data={uart_data},error={e}")

# ===================== 初始化 =====================
print("[INFO] 开始初始化 MaixCAM 系统...")

# 1. 初始化日志模块（最先初始化，确保其他组件可以记录日志）
logger = RunLogger(
    model_name="YOLOv11n",
    input_res=config.INPUT_SIZE,
    enter_N=config.ENTER_THRESHOLD_N,
    exit_M=config.EXIT_THRESHOLD_M
)
print("[OK] 日志模块初始化成功")

# 2. 串口初始化 (用于状态输出)
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
    logger.log_init_failure("uart", str(e))

# 3. 初始化检测器
try:
    detector = Detector()
except Exception as e:
    print(f"[FATAL] 检测器初始化失败: {e}")
    logger.log_init_failure("model", str(e))
    sys.exit(1)

# 4. 初始化状态机
state_machine = StateMachine(on_state_change=on_state_change)

# 5. 初始化摄像头 & 屏幕
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
    logger.log_init_failure("camera", str(e))
    detector.deinit()
    sys.exit(1)

# ===================== 主循环 =====================
print("[BOOT] 启动主循环")

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
            debug_print("Camera returned None image, skipping frame.")
            continue
        
        # 2. 模型推理
        nn_start_s = time.time()
        person_boxes = detector.predict(img)
        nn_end_s = time.time()
        nn_time_s = nn_end_s - nn_start_s
        
        person_count = len(person_boxes)
        debug_print(f"Detected {person_count} persons in {nn_time_s*1000:.2f} ms. Boxes: {[str(box) for box in person_boxes]}")

        # 3. 绘制检测框
        for box in person_boxes:
            img.draw_rect(box.x, box.y, box.w, box.h, color=image.COLOR_RED, thickness=2)
        
        # 4. 状态机逻辑判定
        person_detected = person_count > 0
        
        # 获取当前状态用于事件记录
        prev_state = state_machine.get_state()
        state_changed = state_machine.update(person_detected)
        new_state = state_machine.get_state()
        
        if state_changed:
            debug_print(f"State changed from {prev_state} to {new_state}. Is rollback: {state_machine.get_is_rollback()}")

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

        current_fps = 1.0 / (time.time() - frame_start_s) if (time.time() - frame_start_s) > 0 else 0.0
        debug_print(f"Frame FPS: {current_fps:.2f}")

except KeyboardInterrupt:
    print("[INFO] 程序被用户中断...")
except Exception as e:
    print(f"[FATAL] 主循环发生意外错误: {e}")
    logger.log_error("runtime", "main_loop_exception", extra=str(e))

finally:
    # 8. 程序退出时记录运行日志
    print("[INFO] 正在记录运行日志...")
    logger.write_log()
    print("[INFO] 释放资源并退出。")
    # 资源释放
    if uart1:
        try:
            uart1.close()
        except Exception as e:
            logger.log_error("uart", "uart_close_failed", extra=str(e))
    detector.deinit()
    if cam:
        try:
            cam.close()
        except Exception as e:
            logger.log_error("camera", "camera_close_failed", extra=str(e))
    if disp:
        try:
            disp.close()
        except Exception as e:
            logger.log_error("display", "display_close_failed", extra=str(e))
    sys.exit(0)