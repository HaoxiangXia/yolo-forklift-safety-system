"""
MaixCAM 人员入侵检测系统 - 主程序
整合 camera, display, detector, logic, logger 模块，运行主循环
"""
# -*- coding: utf-8 -*-
import os
import sys
import time
from maix import camera, display, image, uart, pinmap, err
import config
from detector import Detector
from logic import DualROIAlarm
from logger import RunLogger, debug_print
from cloud_reporter import CloudReporter

# ===================== 全局变量 =====================
LAST_HEARTBEAT_TIME_S = 0.0     # 心跳包时间戳（上次发送时间）
LAST_SNAPSHOT_TIME_S = 0.0      # 1 FPS 缓存快照时间
SNAPSHOT_RING = []              # 磁盘环形缓冲路径列表
LAST_RETRY_TICK_S = 0.0         # 图片补传队列上次轮询时间

def calculate_checksum(data):
    """计算轻量级校验和：所有字节累加对 256 取模。"""
    if isinstance(data, str):
        data = data.encode('ascii')
    return sum(data) % 256

def send_packet(cmd_data):
    """高性能组包并发送 UART 数据。格式：<数据内容,十六进制校验和>"""
    if not uart1:
        return

    try:
        if cmd_data == "ALARM:1":
            packet = config.MSG_ALARM_ON
        elif cmd_data == "ALARM:0":
            packet = config.MSG_ALARM_OFF
        elif cmd_data == "HB":
            packet = config.MSG_HB
        else:
            # 动态构建
            checksum = calculate_checksum(cmd_data)
            packet = f"<{cmd_data},{checksum:02X}>".encode()
        
        uart1.write(packet)
    except Exception as e:
        logger.log_uart_failure(reason="uart_write_failed", extra=f"cmd={cmd_data},error={e}")

def _try_delete_snapshot(path):
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logger.log_runtime_exception(reason="snapshot_delete_failed", extra=f"path={path},error={e}")

def _append_snapshot(path):
    global SNAPSHOT_RING
    if not path:
        return
    SNAPSHOT_RING.append(path)
    max_len = getattr(config, "RING_BUFFER_SIZE", 60)
    while len(SNAPSHOT_RING) > max_len:
        dropped = SNAPSHOT_RING.pop(0)
        _try_delete_snapshot(dropped)

def _get_recent_snapshots():
    pre_frames = getattr(config, "PRE_ALARM_FRAMES", 3)
    need = pre_frames + 1
    if need <= 0:
        need = 1
    if not SNAPSHOT_RING:
        return []
    if len(SNAPSHOT_RING) <= need:
        return list(SNAPSHOT_RING)
    return SNAPSHOT_RING[-need:]

def on_alarm_change(alarm_state: bool, center_raw: bool, outer_raw: bool,
                    center_state: bool, outer_state: bool,
                    center_counter, outer_counter,
                    prev_alarm_state: bool, trigger_reason: str, img=None):
    """当报警状态改变时发送 UART 输出并记录日志。"""
    cmd_data = "ALARM:1" if alarm_state else "ALARM:0"
    log_output = "ALARM: ON" if alarm_state else "ALARM: OFF"
    print(f"[STATE CHANGE] {log_output}")

    # 记录状态变化
    logger.log_state_change(
        prev_state=int(prev_alarm_state),
        new_state=int(alarm_state),
        trigger_reason=trigger_reason,
        center_raw=center_raw,
        outer_raw=outer_raw,
        center_state=center_state,
        outer_state=outer_state,
        alarm_state=alarm_state,
        center_counter=center_counter,
        outer_counter=outer_counter
    )

    # 使用优化后的发送函数
    send_packet(cmd_data)

    # 云端上报：仅由 MaixCam 发送 MQTT，ESP32 保留本地执行功能。
    if not cloud_reporter:
        return

    event_ts = cloud_reporter.make_timestamp()
    image_urls = None

    # 仅在 0->1 报警触发时抓图上传；1->0 清警不上报图片。
    # 注意：使用异步上传避免阻塞主循环，图片通过 tick_retry() 后台补传
    if (not prev_alarm_state) and alarm_state:
        snapshot_path = cloud_reporter.save_snapshot(img=img, event_ts=event_ts)
        if snapshot_path:
            _append_snapshot(snapshot_path)

        recent_paths = _get_recent_snapshots()
        if recent_paths:
            # 异步处理：将图片加入重试队列，避免阻塞主循环
            # 图片将在 tick_retry() 中后台上传
            for path in recent_paths:
                cloud_reporter.enqueue_retry(path, event_ts)
            # 首次立即尝试上传获取 URL（非阻塞快速尝试）
            image_urls = cloud_reporter.upload_images_batch(recent_paths, base_timestamp=event_ts)
            if image_urls is None:
                # 上传失败时记录日志，但已加入重试队列，后续会补传
                logger.log_runtime_exception(
                    reason="image_batch_upload_failed_async",
                    extra="alarm_raised_queued_for_retry"
                )
        else:
            logger.log_runtime_exception(
                reason="snapshot_missing_before_publish",
                extra="alarm_raised_but_no_snapshot"
            )
    publish_ok = cloud_reporter.publish_alarm(
        alarm=int(alarm_state),
        timestamp=event_ts,
        image_urls=image_urls
    )
    if not publish_ok:
        logger.log_runtime_exception(
            reason="mqtt_publish_failed",
            extra=f"alarm={int(alarm_state)},timestamp={event_ts}"
        )

# ===================== 初始化 =====================
print("[INFO] 开始初始化 MaixCAM 系统...")

# 1. 初始化日志模块
logger = RunLogger(
    model_path=config.MODEL_PATH,
    input_res=config.INPUT_SIZE
)
print("[OK] 日志模块初始化成功")

# 1.1 初始化云上报模块（HTTP 上传 + MQTT 发布 + 失败补传）
cloud_reporter = None
try:
    cloud_reporter = CloudReporter(logger=logger)
    print("[OK] 云上报模块初始化成功")
    # 启动阶段立即尝试一次 MQTT 连接，失败则直接打印告警。
    if not cloud_reporter.ensure_mqtt_connected():
        print("[ALARM] MQTT 启动连接失败：请检查 broker 地址/端口/网络状态")
except Exception as e:
    print(f"[WARN] 云上报模块初始化失败，将仅保留 UART 本地链路: {e}")
    print("[ALARM] MQTT 模块初始化失败：云端上报不可用")
    logger.log_init_failure("cloud_reporter", str(e))

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
alarm_logic = DualROIAlarm()

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

        # 1 FPS 缓存快照（磁盘环形缓冲）
        snapshot_fps = getattr(config, "SNAPSHOT_FPS", 1)
        snapshot_interval_s = 1.0 / snapshot_fps if snapshot_fps > 0 else 1.0
        if cloud_reporter and (frame_start_s - LAST_SNAPSHOT_TIME_S >= snapshot_interval_s):
            snapshot_ts = cloud_reporter.make_timestamp()
            snapshot_path = cloud_reporter.save_snapshot(img=img, event_ts=snapshot_ts)
            if snapshot_path:
                _append_snapshot(snapshot_path)
                LAST_SNAPSHOT_TIME_S = frame_start_s
        
        # 2. 模型推理
        nn_start_s = time.time()
        person_boxes = detector.predict(img)
        nn_end_s = time.time()
        nn_time_s = nn_end_s - nn_start_s

        person_count = len(person_boxes)
        debug_print(f"Detected {person_count} persons in {nn_time_s*1000:.2f} ms. Boxes: {[str(box) for box in person_boxes]}")

        # 3. 状态机逻辑判定
        frame_w = img.width()
        frame_h = img.height()
        # 最小接入: 在调用 update 前获取状态信息
        # 注意: 这些属性必须由 logic.py 模块真实提供
        prev_alarm_state = getattr(alarm_logic, 'alarm_state', False)
        trigger_reason = "detection_update"

        # 执行逻辑更新
        res = alarm_logic.update(person_boxes, frame_w, frame_h)
        center_raw = res[0]
        outer_raw = res[1]
        center_state = res[2]
        outer_state = res[3]
        alarm_state = res[4]
        state_changed = res[5]

        if state_changed:
            # 从 logic 对象显式获取计数器，若不存在则传 None
            # 注意：此处不再假设 DualROIAlarm 具有这些属性，仅通过 getattr 安全访问并传递
            c_cnt = getattr(alarm_logic, 'center_counter', None)
            o_cnt = getattr(alarm_logic, 'outer_counter', None)
            
            # 调用扩展后的 on_alarm_change 传递所有状态信息
            on_alarm_change(
                alarm_state=alarm_state,
                center_raw=center_raw,
                outer_raw=outer_raw,
                center_state=center_state,
                outer_state=outer_state,
                center_counter=c_cnt,
                outer_counter=o_cnt,
                prev_alarm_state=prev_alarm_state,
                trigger_reason=trigger_reason,
                img=img
            )


        # 4. 绘制图像
        # 检测框
        for box in person_boxes:
            img.draw_rect(box.x, box.y, box.w, box.h, color=image.COLOR_RED, thickness=2)

        # UI
        disp_start_s = time.time()

        # 中心ROI
        roi_x, roi_y, roi_w, roi_h = alarm_logic.get_roi_rect(frame_w, frame_h)
        img.draw_rect(roi_x, roi_y, roi_w, roi_h, color=image.COLOR_BLUE, thickness=2)

        # 状态显示文本
        center_color = image.COLOR_RED if center_state else image.COLOR_GREEN
        outer_color = image.COLOR_RED if outer_state else image.COLOR_GREEN
        alarm_color = image.COLOR_RED if alarm_state else image.COLOR_GREEN

        img.draw_string(10, 10, f"Center: {int(center_raw)}/{int(center_state)}", color=center_color, scale=2)
        img.draw_string(10, 50, f"Outer: {int(outer_raw)}/{int(outer_state)}", color=outer_color, scale=2)
        img.draw_string(10, 90, f"Alarm: {int(alarm_state)}", color=alarm_color, scale=2)

        # 5. 显示最终图像
        disp.show(img)
        disp_end_s = time.time()
        disp_time_s = disp_end_s - disp_start_s

        # 6 定期发送心跳包
        if disp_end_s - LAST_HEARTBEAT_TIME_S > config.HEARTBEAT_INTERVAL_S:
            send_packet("HB")
            LAST_HEARTBEAT_TIME_S = frame_start_s

        # 6.1 后台补传轮询：每秒检查一次，避免阻塞主循环
        if cloud_reporter and (frame_start_s - LAST_RETRY_TICK_S > 1.0):
            cloud_reporter.tick_retry()
            LAST_RETRY_TICK_S = frame_start_s
        
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
    # 使用新的 log_runtime_exception 函数
    logger.log_runtime_exception(reason="main_loop_exception", extra=str(e))

finally:
    # 8. 程序退出时记录运行日志
    print("[INFO] 正在记录运行日志...")
    logger.write_log()
    print("[INFO] 释放资源并退出！")
    # 资源释放
    if uart1:
        try:
            uart1.close()
        except Exception as e:
            # 使用新的 log_uart_failure 函数
            logger.log_uart_failure(reason="uart_close_failed", extra=str(e))
    if cloud_reporter:
        try:
            cloud_reporter.deinit()
        except Exception as e:
            logger.log_runtime_exception(reason="cloud_reporter_deinit_failed", extra=str(e))
    detector.deinit()
    if cam:
        try:
            cam.close()
        except Exception as e:
            # 使用新的 log_runtime_exception 函数
            logger.log_runtime_exception(reason="camera_close_failed", extra=str(e))
    if disp:
        try:
            disp.close()
        except Exception as e:
            # 使用新的 log_runtime_exception 函数
            logger.log_runtime_exception(reason="display_close_failed", extra=str(e))
    sys.exit(0)
