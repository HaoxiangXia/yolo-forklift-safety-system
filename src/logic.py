"""
MaixCAM 人员入侵检测系统 - 状态机逻辑模块
中心 ROI + 外围 ROI 双状态机
"""

# -*- coding: utf-8 -*-
import config

class DebounceStateMachine:
    """
    用于将 raw 信号转换为稳定 state 的简单去抖状态机。
    """

    def __init__(self, on_frames: int, off_frames: int, initial_state: bool = False):
        self.on_frames = max(1, int(on_frames))
        self.off_frames = max(1, int(off_frames))
        self.state = bool(initial_state)
        self._on_count = 0
        self._off_count = 0

    def update(self, raw: bool) -> bool:
        """
        使用 raw 信号更新状态机，并返回状态是否发生变化。"
        """
        changed = False
        if raw:
            # Consecutive hit count
            self._on_count += 1
            self._off_count = 0
            if not self.state and self._on_count >= self.on_frames:
                self.state = True
                changed = True
        else:
            # Consecutive miss count
            self._off_count += 1
            self._on_count = 0
            if self.state and self._off_count >= self.off_frames:
                self.state = False
                changed = True
        return changed


class DualROIAlarm:
    """
    中心/外围 ROI 分类 + 双去抖状态机 + 最终报警判定
    """

    def __init__(self):
        self.center_sm = DebounceStateMachine(config.CENTER_ON_FRAMES, config.CENTER_OFF_FRAMES)
        self.outer_sm = DebounceStateMachine(config.OUTER_ON_FRAMES, config.OUTER_OFF_FRAMES)
        self.alarm_state = False

    def get_roi_rect(self, frame_w: int, frame_h: int):
        """
        根据比例计算中心 ROI 矩形区域
        """
        w = int(frame_w * config.ROI_CENTER_W_RATIO)
        h = int(frame_h * config.ROI_CENTER_H_RATIO)
        if w < 1:
            w = 1
        if h < 1:
            h = 1
        x = int((frame_w - w) / 2)
        y = int((frame_h - h) / 2)
        return x, y, w, h

    def _classify(self, boxes, frame_w: int, frame_h: int):
        """
        根据框中心点将检测框分类到中心/外围 ROI
        """
        x, y, w, h = self.get_roi_rect(frame_w, frame_h)
        x2 = x + w
        y2 = y + h
        center_raw = False
        outer_raw = False
        for box in boxes:
            cx = box.x + (box.w / 2)
            cy = box.y + (box.h / 2)
            if (x <= cx <= x2) and (y <= cy <= y2):
                center_raw = True
            else:
                outer_raw = True
            if center_raw and outer_raw:
                break
        return center_raw, outer_raw

    def update(self, boxes, frame_w: int, frame_h: int):
        """
        主API: 返回 raw、state、alarm、state_changed。
        """
        center_raw, outer_raw = self._classify(boxes, frame_w, frame_h)

        # 更新双状态机
        self.center_sm.update(center_raw)
        self.outer_sm.update(outer_raw)

        center_state = self.center_sm.state
        outer_state = self.outer_sm.state
        alarm_state = bool(center_state and outer_state)

        state_changed = (alarm_state != self.alarm_state)
        self.alarm_state = alarm_state

        return center_raw, outer_raw, center_state, outer_state, alarm_state, state_changed