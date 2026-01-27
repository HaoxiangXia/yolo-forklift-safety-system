"""
MaixCAM 人员入侵检测系统 - 检测器模块
封装 YOLO 模型加载与推理
"""

from maix import nn, err
import config

class Detector:
    """
    检测器类：负责加载 YOLO 模型并对图像进行推理，返回检测到的 'person' 框。
    """

    def __init__(self):
        """
        初始化检测器：加载 YOLO 模型。
        """
        self.model = None
        self.input_width = config.INPUT_SIZE
        self.input_height = config.INPUT_SIZE
        self.input_format = None  # 将由模型设置
        try:
            # 加载模型，使用双缓冲区以提高性能
            self.model = nn.YOLO11(model=config.MODEL_PATH, dual_buff=True)
            # 检查模型输入尺寸
            if self.model.input_width() != config.INPUT_SIZE or self.model.input_height() != config.INPUT_SIZE:
                print(f"[WARN] 模型输入尺寸({self.model.input_width()}x{self.model.input_height()})与预设({config.INPUT_SIZE}x{config.INPUT_SIZE})不匹配！请检查模型配置。")
            # 保存输入格式和尺寸
            self.input_format = self.model.input_format()
            self.input_width = self.model.input_width()
            self.input_height = self.model.input_height()
            print(f"[OK] 检测器初始化成功，模型: {config.MODEL_PATH}")
        except Exception as e:
            print(f"[FATAL] 检测器初始化失败，加载模型失败: {e}")
            raise e

    def predict(self, img):
        """
        对输入图像进行推理，返回检测到的 'person' 框列表。
        Args:
            img: MaixPy 图像对象。
        Returns:
            list: 检测到的 'person' 框列表，每个元素为检测框对象。
        """
        if self.model is None:
            print("[ERROR] 检测器未初始化，无法推理")
            return []
        
        boxes = []
        try:
            # 模型推理
            boxes = self.model.detect(img, conf_th=config.CONFIDENCE_THRESHOLD, iou_th=config.IOU_THRESHOLD)
        except Exception as e:
            print(f"[Inference Error] 推理失败: {e}")
            return []
        
        # 筛选 person 类别
        person_boxes = []
        for box in boxes:
            if box.class_id == config.PERSON_CLASS_ID:
                person_boxes.append(box)
        
        return person_boxes

    def deinit(self):
        """
        释放模型资源。
        """
        if self.model:
            # MaixPy4 的 nn.YOLOv8 没有 deinit 方法，直接置空即可
            self.model = None
            print("[OK] 检测器资源已释放")