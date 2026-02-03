"""
MaixCAM 人员入侵检测系统 - 状态机逻辑模块
封装“进入计数 N=5 / 退出计数 M=8”状态机逻辑
"""

import config

class StateMachine:
    """
    状态机类：实现“进入计数 N=5 / 退出计数 M=8”逻辑，并提供状态切换回调。
    """

    def __init__(self, on_state_change=None):
        """
        初始化状态机。
        Args:
            on_state_change (callable, optional): 状态切换时的回调函数，参数为 (new_state, is_rollback)。
        """
        self.current_state = config.STATE_IDLE
        self.enter_frame_count = 0
        self.exit_frame_count = 0
        self.on_state_change = on_state_change
        self._is_rollback = False # 新增私有属性用于存储is_rollback状态

    def update(self, person_detected: bool) -> bool:
        """
        根据检测结果更新状态机，返回状态是否发生变化。
        Args:
            person_detected (bool): 是否检测到 person。
        Returns:
            bool: 状态是否发生变化。
        """
        new_state = self.current_state
        self._is_rollback = False # 每次更新前重置

        if person_detected:
            # 检测到人: 增加进入计数, 重置退出计数
            self.enter_frame_count += 1
            self.exit_frame_count = 0

            # 只有在 Idle 状态下，达到 N 阈值才切换到 Intrusion
            if self.current_state == config.STATE_IDLE and self.enter_frame_count >= config.ENTER_THRESHOLD_N:
                new_state = config.STATE_INTRUSION
                
        else:
            # 未检测到人: 增加退出计数, 重置进入计数
            self.enter_frame_count = 0
            self.exit_frame_count += 1

            # 只有在 Intrusion 状态下，达到 M 阈值才切换到 Idle
            if self.current_state == config.STATE_INTRUSION and self.exit_frame_count >= config.EXIT_THRESHOLD_M:
                new_state = config.STATE_IDLE

        # 检查状态是否发生变化
        if new_state != self.current_state:
            # 判断是否为误触发回滚（进入后很快退出）
            self._is_rollback = (self.current_state == config.STATE_INTRUSION and new_state == config.STATE_IDLE and self.enter_frame_count < config.ENTER_THRESHOLD_N)
            
            self.current_state = new_state
            
            # 调用状态切换回调
            if self.on_state_change:
                self.on_state_change(new_state, self._is_rollback, self.current_state, self.enter_frame_count, self.exit_frame_count)
            
            return True
        
        return False

    def get_state(self):
        """
        获取当前状态。
        Returns:
            int: 当前状态（STATE_IDLE 或 STATE_INTRUSION）。
        """
        return self.current_state

    def get_counts(self):
        """
        获取当前计数信息。
        Returns:
            tuple: (enter_frame_count, exit_frame_count)
        """
        return (self.enter_frame_count, self.exit_frame_count)

    def get_is_rollback(self) -> bool:
        """
        获取当前帧是否发生回滚。
        Returns:
            bool: 是否为回滚状态。
        """
        return self._is_rollback