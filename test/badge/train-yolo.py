from ultralytics import YOLO
import torch

def main():
    # =========================
    # 1. 基础配置
    # =========================

    # 使用轻量模型，小数据集不要用大模型
    MODEL_NAME = "yolo11n.pt"

    # 数据集配置文件路径
    DATA_YAML = "datasets/data.yaml"

    # 训练轮数（小数据集不要太大，防止过拟合）
    EPOCHS = 100

    # 输入尺寸
    # 小目标 / 鱼眼 → 640 比较稳
    IMG_SIZE = 640

    # batch 太大反而不稳定，小数据集推荐 4~8
    BATCH_SIZE = 4

    # =========================
    # 2. 环境检查
    # =========================
    print("PyTorch version:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())

    # =========================
    # 3. 加载模型
    # =========================
    # 会自动下载权重（如果本地没有）
    model = YOLO(MODEL_NAME)

    # =========================
    # 4. 开始训练
    # =========================
    model.train(
        data=DATA_YAML,      # 数据集配置
        epochs=EPOCHS,       # 训练轮数
        imgsz=IMG_SIZE,      # 输入分辨率
        batch=BATCH_SIZE,    # batch size
        device=0,            # GPU:0；CPU 写 "cpu"
        workers=2,           # 数据加载线程，小数据集不宜太大
        optimizer="AdamW",   # 小数据集更稳定
        lr0=1e-3,            # 初始学习率（小数据集不要太大）
        patience=30,         # 早停：30 轮没提升就停
        cos_lr=True,         # 余弦退火，训练更平滑
        close_mosaic=10,     # 最后 10 轮关闭 mosaic，收敛更稳
        verbose=True,        # 显示训练日志
        single_cls=True      # ⭐ 关键：单类别模式（非常重要）
    )

    # =========================
    # 5. 训练完成提示
    # =========================
    print("Training finished!⭐")
    print("Best model saved at: runs/detect/train/weights/best.pt")

if __name__ == "__main__":
    main()
