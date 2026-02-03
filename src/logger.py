import time
import os
import ujson as json # MaixPy4 usually uses ujson for embedded JSON needs
import config # 导入config模块以获取DEBUG配置

# ===================== 配置 =====================
LOG_DIR = "/root/logs"
FPS_WINDOW_SIZE = 30 # 滑动窗口大小，用于计算窗口平均 FPS
LOW_FPS_THRESHOLD_FPS = 20.0 # 低于此帧率（例如 20 FPS）计入低帧率统计
LOW_FPS_TIME_THRESHOLD_S = 1.0 / LOW_FPS_THRESHOLD_FPS # 0.05 秒 (50 毫秒)

# ===================== 事件日志配置 =====================
EVENT_STATE_CHANGE = "STATE_CHANGE"
EVENT_INIT_FAILURE = "INIT_FAILURE"
EVENT_UART_ERROR = "UART_ERROR"
EVENT_RUNTIME_ERROR = "RUNTIME_ERROR"


def debug_print(*args, **kwargs):
    """
    Debug模式下的print输出，受config.DEBUG控制。
    Args:
        *args: 传递给print的参数
        **kwargs: 传递给print的关键字参数
    """
    if config.DEBUG:
        print("[DEBUG]", *args, **kwargs)


class RunLogger:
    """
    可复用的 MaixPy4 运行日志与性能统计模块。
    负责记录程序配置、运行统计、性能耗时、状态机事件，并输出 .log 和 .csv 文件。
    """
    
    def __init__(self, model_name: str, input_res: int, enter_N: int, exit_M: int):
        """
        初始化日志系统。
        Args:
            model_name (str): 模型名称，例如 "YOLOv11n"。
            input_res (int): 模型输入分辨率，例如 832。
            enter_N (int): 状态机进入阈值 N。
            exit_M (int): 状态机退出阈值 M。
        """
        self.model_name = model_name
        self.input_res = input_res
        self.enter_N = enter_N
        self.exit_M = exit_M

        # 统计数据
        self.total_frames = 0           # 总处理帧数
        self.start_time_s = time.time() # 程序启动时间
        self.last_frame_time_s = self.start_time_s # 上一帧结束时间，用于计算瞬时帧率/低帧率统计
        self.low_fps_frames_count = 0   # 帧率低于阈值 (LOW_FPS_THRESHOLD_FPS) 的帧数
        
        # FPS 统计 (滑动窗口)
        self.frame_times_s = []
        self.min_window_avg_fps = float('inf')
        self.max_window_avg_fps = 0.0

        # 耗时累计 (总和，单位：秒)
        self.time_cam_total_s = 0.0
        self.time_nn_total_s = 0.0
        self.time_disp_total_s = 0.0
        self.time_other_total_s = 0.0
        
        # 状态机统计
        self.intrusion_enters = 0
        self.intrusion_exits = 0
        self.false_trigger_rollbacks = 0 
        
        # 时间戳用于日志文件名
        self.timestamp = time.strftime('%Y%m%d_%H%M%S', time.localtime())

    def record_frame(self, time_cam: float, time_nn: float, time_disp: float, time_other: float):
        """
        每帧调用，记录各阶段耗时并更新 FPS 统计。
        Args:
            time_cam (float): 相机采集耗时 (秒)。
            time_nn (float): YOLO 推理耗时 (秒)。
            time_disp (float): 显示/绘制耗时 (秒)。
            time_other (float): 其他逻辑耗时 (秒)。
        """
        current_time = time.time()
        self.frame_times_s.append(current_time)
        self.total_frames += 1

        # 统计低帧率帧（基于帧间隔时间）
        frame_duration_s = current_time - self.last_frame_time_s
        if frame_duration_s > LOW_FPS_TIME_THRESHOLD_S:
            self.low_fps_frames_count += 1 # 帧间隔过长，计为低帧率
        self.last_frame_time_s = current_time
        
        self.time_cam_total_s += time_cam
        self.time_nn_total_s += time_nn
        self.time_disp_total_s += time_disp
        self.time_other_total_s += time_other

        # 滑动窗口 FPS 统计
        if len(self.frame_times_s) > FPS_WINDOW_SIZE:
            self.frame_times_s.pop(0)
        
        if len(self.frame_times_s) >= FPS_WINDOW_SIZE:
            # 计算窗口平均 FPS
            time_diff_s = self.frame_times_s[-1] - self.frame_times_s[0]
            if time_diff_s > 0:
                window_avg_fps = (FPS_WINDOW_SIZE - 1) / time_diff_s
                
                # 更新最大/最小窗口平均 FPS
                if window_avg_fps > self.max_window_avg_fps:
                    self.max_window_avg_fps = window_avg_fps
                # 忽略初始 inf 值
                if window_avg_fps < self.min_window_avg_fps and self.min_window_avg_fps != float('inf'):
                     self.min_window_avg_fps = window_avg_fps
                # 首次设置 min_window_avg_fps
                if self.min_window_avg_fps == float('inf'):
                    self.min_window_avg_fps = window_avg_fps
    
    def record_state_change(self, state_type: str, is_rollback: bool = False):
        """
        记录状态机变化事件。
        Args:
            state_type (str): "INTRUSION_ENTER" 或 "IDLE_EXIT"。
            is_rollback (bool): 是否为误触发回滚（即进入后短时间内退出）。
        """
        if state_type == "INTRUSION_ENTER":
            self.intrusion_enters += 1
        elif state_type == "IDLE_EXIT":
            self.intrusion_exits += 1
        
        if is_rollback:
            self.false_trigger_rollbacks += 1

    def _log_event(self, event_type: str, trigger_reason: str, prev_state=None, new_state=None,
                   person_count=None, state_counter=None, extra=None):
        """
        记录事件日志，使用结构化输出
        Args:
            event_type: 事件类型
            trigger_reason: 触发原因
            prev_state: 前一状态（可选）
            new_state: 新状态（可选）
            person_count: 检测到的人数（可选）
            state_counter: 状态机计数（可选）
            extra: 额外信息（可选）
        """
        event_log = {
            "timestamp_ms": int(time.time() * 1000),
            "event_type": event_type,
            "trigger_reason": trigger_reason,
            "prev_state": prev_state,
            "new_state": new_state,
            "person_count": person_count,
            "state_counter": state_counter,
            "extra": extra
        }
        
        # 使用key=value格式输出，便于嵌入式系统解析
        log_parts = []
        for key, value in event_log.items():
            if value is not None:
                log_parts.append(f"{key}={value}")
            else:
                log_parts.append(f"{key}=None")
        
        print("[EVENT] " + " ".join(log_parts))

    def log_state_change(self, prev_state: int, new_state: int, trigger_reason: str,
                        person_count: int = 0, state_counter: int = 0, extra: str = ""):
        """
        记录状态机切换事件
        Args:
            prev_state: 前一状态
            new_state: 新状态
            trigger_reason: 触发原因
            person_count: 检测到的人数
            state_counter: 状态机计数
            extra: 额外信息
        """
        self._log_event(
            event_type=EVENT_STATE_CHANGE,
            trigger_reason=trigger_reason,
            prev_state=prev_state,
            new_state=new_state,
            person_count=person_count,
            state_counter=state_counter,
            extra=extra
        )

    def log_init_failure(self, component: str, reason: str, extra: str = ""):
        """
        记录初始化失败事件
        Args:
            component: 失败的组件（camera/model/uart等）
            reason: 失败原因
            extra: 额外信息
        """
        self._log_event(
            event_type=EVENT_INIT_FAILURE,
            trigger_reason=f"{component}_init_failed",
            extra=f"reason={reason}" + (f";{extra}" if extra else "")
        )

    def log_error(self, error_type: str, reason: str, extra: str = ""):
        """
        记录运行错误事件
        Args:
            error_type: 错误类型（uart/runtime等）
            reason: 错误原因
            extra: 额外信息
        """
        event_type = EVENT_UART_ERROR if error_type == "uart" else EVENT_RUNTIME_ERROR
        self._log_event(
            event_type=event_type,
            trigger_reason=reason,
            extra=extra
        )

    def _generate_text_log(self, end_time_s: float, total_run_time_s: float) -> str:
        """生成结构化的文本日志内容 (.log)"""
        
        # 1. 计算平均耗时
        num_frames = self.total_frames if self.total_frames > 0 else 1 # Avoid division by zero
        avg_cam_ms = (self.time_cam_total_s / num_frames) * 1000
        avg_nn_ms = (self.time_nn_total_s / num_frames) * 1000
        avg_disp_ms = (self.time_disp_total_s / num_frames) * 1000
        avg_other_ms = (self.time_other_total_s / num_frames) * 1000
        
        # 2. 计算总平均 FPS
        total_avg_fps = self.total_frames / total_run_time_s if total_run_time_s > 0 else 0
        
        min_fps_display = self.min_window_avg_fps if self.min_window_avg_fps != float('inf') else 0.0

        log_content = f"""
==================== MaixCAM 运行日志 ====================
程序启动时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.start_time_s))}
程序退出时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time_s))}

-------------------- 配置信息 --------------------
模型名称: {self.model_name}
输入分辨率: {self.input_res}x{self.input_res}
状态机 N (进入阈值): {self.enter_N}
状态机 M (退出阈值): {self.exit_M}

-------------------- 运行统计 --------------------
总运行帧数: {self.total_frames}
总运行时长: {total_run_time_s:.2f} 秒

-------------------- FPS 统计 (滑动窗口 {FPS_WINDOW_SIZE} 帧) --------------------
总平均 FPS: {total_avg_fps:.2f}
窗口最大平均 FPS: {self.max_window_avg_fps:.2f}
窗口最小平均 FPS: {min_fps_display:.2f}

-------------------- 阶段耗时 (平均 / 毫秒) --------------------
相机采集平均耗时: {avg_cam_ms:.2f} ms
YOLO 推理平均耗时: {avg_nn_ms:.2f} ms
显示/绘制平均耗时: {avg_disp_ms:.2f} ms
其他逻辑平均耗时: {avg_other_ms:.2f} ms

-------------------- 状态机统计 --------------------
入侵状态进入次数: {self.intrusion_enters}
入侵状态退出次数: {self.intrusion_exits}
误触发回滚次数: {self.false_trigger_rollbacks}
==========================================================
"""
        return log_content

    def _generate_csv_log(self, total_avg_fps: float, avg_nn_ms: float, avg_disp_ms: float, low_fps_ratio: float) -> str:
        """生成核心指标的 CSV 日志内容 (包含 12 项指定指标)"""
        
        min_fps_display = self.min_window_avg_fps if self.min_window_avg_fps != float('inf') else 0.0
        
        # 定义 CSV 头部，包含 12 项指定指标，顺序与用户要求一致，配置项优先
        header = [
            "model_name",                   # 模型名称
            "imgsz",                        # 输入分辨率 (例如 832)
            "N",                            # 状态机 N (进入阈值)
            "M",                            # 状态机 M (退出阈值)
            "avg_fps",                      # 总平均 FPS
            "min_fps_window",               # 窗口最小平均 FPS
            "low_fps_ratio",                # 低于阈值 FPS 的帧数占比 (%)
            "detect_ms_avg",                # YOLO 推理平均耗时 (ms)
            "display_ms_avg",               # 显示/绘制平均耗时 (ms)
            "enter_cnt",                    # 状态机进入次数
            "exit_cnt",                     # 状态机退出次数
            "rollback_cnt",                 # 误触发回滚次数
        ]
        
        # 准备数据行
        data = [
            self.model_name,
            self.input_res,
            self.enter_N,
            self.exit_M,
            f"{total_avg_fps:.2f}",
            f"{min_fps_display:.2f}",
            f"{low_fps_ratio:.2f}",
            f"{avg_nn_ms:.2f}",
            f"{avg_disp_ms:.2f}",
            self.intrusion_enters,
            self.intrusion_exits,
            self.false_trigger_rollbacks
        ]
        
        csv_content = ",".join(header) + "\n" + ",".join(map(str, data))
        return csv_content
        
    def write_log(self):
        """程序退出时统一调用，写入 .log 和 .csv 文件"""
        
        end_time_s = time.time()
        total_run_time_s = end_time_s - self.start_time_s
        
        if self.total_frames == 0 or total_run_time_s < 0.1:
            print("[Logger] No sufficient frames processed, skipping log file creation.")
            return
            
        # 1. 计算平均耗时 (用于日志)
        num_frames = self.total_frames
        total_avg_fps = self.total_frames / total_run_time_s
        avg_cam_ms = (self.time_cam_total_s / num_frames) * 1000
        avg_nn_ms = (self.time_nn_total_s / num_frames) * 1000
        avg_disp_ms = (self.time_disp_total_s / num_frames) * 1000
        # avg_other_ms is already calculated implicitly in the _generate_text_log function logic

        # 2. 生成日志内容
        log_content = self._generate_text_log(end_time_s, total_run_time_s)
        avg_other_ms = (self.time_other_total_s / num_frames) * 1000 # 其他逻辑平均耗时
        
        # 新增：计算低帧率占比 (低于 LOW_FPS_THRESHOLD_FPS 的帧数 / 总帧数)
        low_fps_ratio = (self.low_fps_frames_count / num_frames) * 100.0 if num_frames > 0 else 0.0
        
        csv_content = self._generate_csv_log(total_avg_fps, avg_nn_ms, avg_disp_ms, low_fps_ratio)

        # 3. 写入文件
        try:
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR)
            
            # 写入 .log 文件
            log_file_path = os.path.join(LOG_DIR, f"run_{self.timestamp}.log")
            with open(log_file_path, 'w') as f:
                f.write(log_content)
            print(f"[Logger] 结构化日志已保存至: {log_file_path}")
            
            # 写入 .csv 文件
            csv_file_path = os.path.join(LOG_DIR, f"summary_{self.timestamp}.csv")
            with open(csv_file_path, 'w') as f:
                f.write(csv_content)
            print(f"[Logger] CSV 摘要已保存至: {csv_file_path}")

        except Exception as e:
            print(f"[Logger FATAL] 写入日志失败，请检查文件系统权限: {e}")
