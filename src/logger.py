# -*- coding: utf-8 -*-
import os
import time
import ujson as json # MaixPy4 通常使用 ujson 处理嵌入式 JSON 需求
import config

# ===================== 配置 =====================
LOG_DIR = "/root/logs"
FPS_WINDOW_SIZE = 25  # 滑动窗口大小，用于计算窗口平均 FPS
LOW_FPS_THRESHOLD_FPS = 20.0  # 低帧率阈值
LOW_FPS_TIME_THRESHOLD_S = 1.0 / LOW_FPS_THRESHOLD_FPS  # 低 FPS 的时间阈值

# ===================== 事件日志配置 =====================
EVENT_STATE_CHANGE = "STATE_CHANGE"
EVENT_INIT_FAILURE = "INIT_FAILURE"
EVENT_UART_ERROR = "UART_ERROR"
EVENT_RUNTIME_ERROR = "RUNTIME_ERROR"


def debug_print(*args, **kwargs):
    """
    仅在 config.DEBUG 为 True 时打印调试信息。
    """
    if getattr(config, 'DEBUG', False):
        print("[DEBUG]", *args, **kwargs)


class RunLogger:
    """
    运行日志与性能统计：
    - 记录配置与性能数据
    - 记录状态机事件 (控制台输出 + 文件追加)
    - 退出时写入汇总 .log 和 .csv 文件
    """

    def __init__(self, model_path: str, input_res: int):
        # 基础信息
        self.model_path = model_path
        self.input_res = input_res

        # 运行统计
        self.total_frames = 0
        self.start_time_s = time.time()
        self.last_frame_time_s = self.start_time_s
        self.low_fps_frames_count = 0

        # FPS 统计 (滑动窗口)
        self.frame_times_s = []
        self.min_window_avg_fps = float("inf")
        self.max_window_avg_fps = 0.0

        # 耗时统计 (秒)
        self.time_cam_total_s = 0.0
        self.time_nn_total_s = 0.0
        self.time_disp_total_s = 0.0
        self.time_other_total_s = 0.0

        # 状态机统计
        self.intrusion_enters = 0
        self.intrusion_exits = 0
        self.false_trigger_rollbacks = 0

        # 用于日志文件名的系统时间戳
        lt = time.localtime()
        self.timestamp = time.strftime("%Y%m%d_%H%M%S", lt)  #格式YYYYMMDD_HHMMSS
        
        # 事件日志文件路径
        if not os.path.exists(LOG_DIR):
            try:
                os.makedirs(LOG_DIR)
            except:
                pass
        self.event_log_path = os.path.join(LOG_DIR, f"events_{self.timestamp}.log")

    def record_frame(self, time_cam: float, time_nn: float, time_disp: float, time_other: float):
        """记录每帧耗时并更新 FPS 统计。"""
        current_time = time.time()
        self.frame_times_s.append(current_time)
        self.total_frames += 1

        # 低帧率检查
        frame_duration_s = current_time - self.last_frame_time_s
        if frame_duration_s > LOW_FPS_TIME_THRESHOLD_S:
            self.low_fps_frames_count += 1
        self.last_frame_time_s = current_time

        # 累加耗时
        self.time_cam_total_s += time_cam
        self.time_nn_total_s += time_nn
        self.time_disp_total_s += time_disp
        self.time_other_total_s += time_other

        # 维护滑动窗口
        if len(self.frame_times_s) > FPS_WINDOW_SIZE:
            self.frame_times_s.pop(0)

        # 计算窗口平均 FPS
        if len(self.frame_times_s) >= FPS_WINDOW_SIZE:
            time_diff_s = self.frame_times_s[-1] - self.frame_times_s[0]
            if time_diff_s > 0:
                window_avg_fps = (FPS_WINDOW_SIZE - 1) / time_diff_s
                if window_avg_fps > self.max_window_avg_fps:
                    self.max_window_avg_fps = window_avg_fps
                if window_avg_fps < self.min_window_avg_fps and self.min_window_avg_fps != float("inf"):
                    self.min_window_avg_fps = window_avg_fps
                if self.min_window_avg_fps == float("inf"):
                    self.min_window_avg_fps = window_avg_fps

    def record_state_change(self, state_type: str, is_rollback: bool = False):
        """记录状态机切换统计。"""
        if state_type == "INTRUSION_ENTER":
            self.intrusion_enters += 1
        elif state_type == "IDLE_EXIT":
            self.intrusion_exits += 1
        if is_rollback:
            self.false_trigger_rollbacks += 1

    def _log_event(self, event_type: str, trigger_reason: str, prev_state=None, new_state=None,
                   center_raw=None, outer_raw=None, center_state=None, outer_state=None,
                   alarm_state=None, center_counter=None, outer_counter=None, extra=None):
        """
        统一的事件日志输出。
        - 格式：key=value 单行字符串
        - 输出：控制台 print + 追加写入 events_*.log 文件
        - 字段：固定 13 个字段，不适用填 None
        """
        event_log = {
            "timestamp_ms": int(time.time() * 1000),
            "event_type": event_type,
            "trigger_reason": trigger_reason,
            "prev_state": prev_state,
            "new_state": new_state,
            "center_raw": center_raw,
            "outer_raw": outer_raw,
            "center_state": center_state,
            "outer_state": outer_state,
            "alarm_state": alarm_state,
            "center_counter": center_counter,
            "outer_counter": outer_counter,
            "extra": extra,
        }

        # 序列化为 key=value 格式
        log_parts = []
        for key, value in event_log.items():
            log_parts.append(f"{key}={value}")
        log_line = "[EVENT] " + " ".join(log_parts)
        
        # 1. 控制台输出 (不受 config.DEBUG 影响)
        print(log_line)
        
        # 2. 追加写入文件
        try:
            with open(self.event_log_path, "a") as f:
                f.write(log_line + "\n")
        except:
            pass

    def log_state_change(self, prev_state: int, new_state: int, trigger_reason: str,
                         center_raw=None, outer_raw=None, center_state=None, outer_state=None,
                         alarm_state=None, center_counter=None, outer_counter=None, extra: str = ""):
        """记录状态机切换事件。"""
        self._log_event(
            event_type=EVENT_STATE_CHANGE,
            trigger_reason=trigger_reason,
            prev_state=prev_state,
            new_state=new_state,
            center_raw=center_raw,
            outer_raw=outer_raw,
            center_state=center_state,
            outer_state=outer_state,
            alarm_state=alarm_state,
            center_counter=center_counter,
            outer_counter=outer_counter,
            extra=extra,
        )

    def log_init_failure(self, component: str, reason: str, extra: str = ""):
        """记录初始化失败事件。"""
        self._log_event(
            event_type=EVENT_INIT_FAILURE,
            trigger_reason=f"{component}_init_failed",
            extra=f"reason={reason}" + (f";{extra}" if extra else ""),
        )

    def log_error(self, error_type: str, reason: str, extra: str = ""):
        """记录运行时错误日志 (保持旧接口兼容)。"""
        event_type = EVENT_UART_ERROR if error_type == "uart" else EVENT_RUNTIME_ERROR
        self._log_event(
            event_type=event_type,
            trigger_reason=reason,
            extra=extra,
        )

    def log_uart_failure(self, reason: str, extra: str = ""):
        """UART 失败日志封装。"""
        self._log_event(
            event_type=EVENT_UART_ERROR,
            trigger_reason=reason,
            extra=extra,
        )

    def log_runtime_exception(self, reason: str, extra: str = ""):
        """通用运行时异常日志封装。"""
        self._log_event(
            event_type=EVENT_RUNTIME_ERROR,
            trigger_reason=reason,
            extra=extra,
        )

    def _generate_text_log(self, end_time_s: float, total_run_time_s: float) -> str:
        """生成汇总 .log 文本内容。"""
        num_frames = self.total_frames if self.total_frames > 0 else 1
        avg_cam_ms = (self.time_cam_total_s / num_frames) * 1000
        avg_nn_ms = (self.time_nn_total_s / num_frames) * 1000
        avg_disp_ms = (self.time_disp_total_s / num_frames) * 1000
        avg_other_ms = (self.time_other_total_s / num_frames) * 1000

        total_avg_fps = self.total_frames / total_run_time_s if total_run_time_s > 0 else 0
        min_fps_display = self.min_window_avg_fps if self.min_window_avg_fps != float("inf") else 0.0

        log_content = f"""
==================== MaixCAM Runtime Log ====================
开始时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.start_time_s))}
结束时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time_s))}

-------------------- 配置 --------------------
模型路径: {self.model_path}
输入分辨率: {self.input_res}x{self.input_res}
ROI 中心宽度占比: {getattr(config, 'ROI_CENTER_W_RATIO', 'None')}
ROI 中心高度占比: {getattr(config, 'ROI_CENTER_H_RATIO', 'None')}
中心进入帧数 (CENTER_ON): {getattr(config, 'CENTER_ON_FRAMES', 'None')}
中心退出帧数 (CENTER_OFF): {getattr(config, 'CENTER_OFF_FRAMES', 'None')}
外围进入帧数 (OUTER_ON): {getattr(config, 'OUTER_ON_FRAMES', 'None')}
外围退出帧数 (OUTER_OFF): {getattr(config, 'OUTER_OFF_FRAMES', 'None')}

-------------------- 运行统计 --------------------
总帧数: {self.total_frames}
运行总时长: {total_run_time_s:.2f} s

-------------------- FPS 统计 (窗口 {FPS_WINDOW_SIZE} 帧) --------------------
平均 FPS: {total_avg_fps:.2f}
窗口最大 FPS: {self.max_window_avg_fps:.2f}
窗口最小 FPS: {min_fps_display:.2f}

-------------------- 阶段平均耗时 (ms) --------------------
摄像头: {avg_cam_ms:.2f} ms
模型推理: {avg_nn_ms:.2f} ms
显示渲染: {avg_disp_ms:.2f} ms
其他: {avg_other_ms:.2f} ms

-------------------- 状态机统计 --------------------
入侵进入次数: {self.intrusion_enters}
空闲退出次数: {self.intrusion_exits}
误报回退次数: {self.false_trigger_rollbacks}
==========================================================
"""
        return log_content

    def _generate_csv_log(self, total_avg_fps: float, avg_nn_ms: float, avg_disp_ms: float, low_fps_ratio: float) -> str:
        """生成汇总 .csv 内容。"""
        min_fps_display = self.min_window_avg_fps if self.min_window_avg_fps != float("inf") else 0.0

        header = [
            "model_path",
            "imgsz",
            "center_on",
            "center_off",
            "outer_on",
            "outer_off",
            "avg_fps",
            "min_fps_window",
            "low_fps_ratio",
            "detect_ms_avg",
            "display_ms_avg",
            "enter_cnt",
            "exit_cnt",
            "rollback_cnt",
        ]

        data = [
            self.model_path,
            self.input_res,
            getattr(config, 'CENTER_ON_FRAMES', 'None'),
            getattr(config, 'CENTER_OFF_FRAMES', 'None'),
            getattr(config, 'OUTER_ON_FRAMES', 'None'),
            getattr(config, 'OUTER_OFF_FRAMES', 'None'),
            f"{total_avg_fps:.2f}",
            f"{min_fps_display:.2f}",
            f"{low_fps_ratio:.2f}",
            f"{avg_nn_ms:.2f}",
            f"{avg_disp_ms:.2f}",
            self.intrusion_enters,
            self.intrusion_exits,
            self.false_trigger_rollbacks,
        ]

        return ",".join(header) + "\n" + ",".join(map(str, data))

    def write_log(self):
        """退出时写入汇总日志文件。"""
        end_time_s = time.time()
        total_run_time_s = end_time_s - self.start_time_s

        if self.total_frames == 0 or total_run_time_s < 0.1:
            print("[Logger] 帧数不足，跳过汇总日志写入。")
            return

        # 计算平均值
        num_frames = self.total_frames
        total_avg_fps = self.total_frames / total_run_time_s
        avg_nn_ms = (self.time_nn_total_s / num_frames) * 1000
        avg_disp_ms = (self.time_disp_total_s / num_frames) * 1000

        # 构建文本日志
        log_content = self._generate_text_log(end_time_s, total_run_time_s)

        # 低帧率比例
        low_fps_ratio = (self.low_fps_frames_count / num_frames) * 100.0 if num_frames > 0 else 0.0

        # CSV 摘要
        csv_content = self._generate_csv_log(total_avg_fps, avg_nn_ms, avg_disp_ms, low_fps_ratio)

        # 写入文件
        try:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR)

            # 写入 run_*.log
            sum_log_path = os.path.join(LOG_DIR, f"run_{self.timestamp}.log")
            with open(sum_log_path, "w") as f:
                f.write(log_content)
            print(f"[Logger] 汇总日志已保存: {sum_log_path}")

            # 写入 summary_*.csv
            csv_file_path = os.path.join(LOG_DIR, f"summary_{self.timestamp}.csv")
            with open(csv_file_path, "w") as f:
                f.write(csv_content)
            print(f"[Logger] CSV 摘要已保存: {csv_file_path}")

        except Exception as e:
            print(f"[Logger FATAL] 写入日志失败: {e}")
