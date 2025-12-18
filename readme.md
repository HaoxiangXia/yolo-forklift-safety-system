# YSU2026大创项目-基于YOLO的叉车作业人车互斥报警系统设计与实现

用前说明：建议ssh连接git ↓
```
ssh -T git@github.com
```

### 初步项目架构规划
```
鱼眼相机 → 上位机（PC/树莓派/Jetson跑YOLO）
                    ↓
              串口 / USB / 网口
                    ↓
               MCU（STM32/ESP32）
                    ↓
              蜂鸣器 / 继电器 / 报警灯
```

---

### 使用X-AnyLabeling-3.3.2进行标注
https://github.com/CVHub520/X-AnyLabeling

---
---

# 探索与踩坑过程（从环境搭建到结果验证）

## 一、环境搭建过程

### 1. 创建 Conda 虚拟环境

```bash
conda create -n yolo python=3.9
conda activate yolo
```

* 使用 Python 3.9
* 单独环境避免依赖冲突

### 2. 安装 Ultralytics YOLO

```bash
pip install ultralytics
```

安装完成后可通过以下命令验证：

```bash
yolo version
```

---

## 二、在 VS Code 中运行 YOLO

* 使用 VS Code 的 **终端（PowerShell）**
* 确保 VS Code 使用的是 Conda 环境 `yolo`
* 成功运行 `yolo` 命令后，说明 CLI 可用

常见问题：

* `conda` 或 `yolo` 命令无法识别 → 通常是环境未激活或 PATH 未加载
* PowerShell 执行策略导致脚本报错 → 属于 Windows 常见问题

---

## 三、YOLO 版本与模型说明

* 使用的是 **Ultralytics YOLO 框架**
https://github.com/ultralytics/ultralytics
* 训练模型为：yolo11n.pt

**说明：**
> YOLO11 是 Ultralytics 在 YOLOv8 基础上推出的新一代 YOLO 架构。相比 YOLOv8，YOLO11 在网络结构上引入了新的模块与注意力机制，在参数量更小的情况下提升了检测精度和推理效率。本项目中采用 YOLO11n 模型进行训练，更适合小数据集和初学者实验

---

## 四、训练所用数据集结构

```text
datasets/mydata/
├─ images/
│  ├─ train/   # 45 张图片
│  └─ val/     # 13 张图片
├─ labels/
│  ├─ train/
│  └─ val/
└─ data.yaml
```

> 注意：训练时报错 `data.yaml does not exist` 的问题，最终确认是 **路径不正确或文件名不一致** 导致。

---

## 五、模型训练过程

训练命令示例：

```bash
yolo train model=yolo11n.pt data=data.yaml epochs=50 imgsz=640
```

训练过程中观察到：

* 成功扫描数据集：

  * Train：45 images
  * Val：13 images
* YOLO 自动修复了部分 **损坏的 JPEG 图片**
* 成功使用 GPU（RTX 4060 Laptop）

---

## 六、验证与结果分析

### 1. 验证结果

```text
Images: 13
Instances: 13
Precision: 0.997
Recall: 0.995
mAP50: 0.995
mAP50-95: 0.907
```

### 2. 分析

* 验证使用的是 `best.pt`
* 指标非常高

---

## 七、是否存在过拟合？

综合判断：

* 数据集规模较小（共 58 张）
* 验证集数量更小（13 张）
* 验证指标接近满分

结论：

> **模型存在较高的过拟合风险，但不一定已经严重过拟合。**

是否真正过拟合，需要进一步通过：

* 使用“完全未见过的新图片”进行预测
* 观察训练/验证 loss 曲线
* 扩充数据集规模

---

## 八、截至目前的收获

* 完整跑通了 YOLO 自定义训练流程
* 理解了：

  * YOLO CLI 使用方式
  * data.yaml 的作用
  * 训练集 vs 验证集的区别
  * 小数据集高 mAP ≠ 泛化能力强
* 为后续：

  * 数据集扩展
  * 模型对比（YOLOv8 / YOLO11）
  * 嵌入式或工程部署

打下了基础

---

写给自己的提醒：打开哪个文件夹就会在哪个文件夹下生成runs
