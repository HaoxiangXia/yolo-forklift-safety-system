# YSU2026大创项目-基于YOLO的叉车作业人车互斥报警系统设计与实现

用前说明：强烈建议ssh连接git ↓
```
ssh -T git@github.com
```

### 初步项目架构
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

### 使用YOLO v8 (YOLO11n)训练
https://github.com/ultralytics/ultralytics

---

### 使用X-AnyLabeling-3.3.2进行标注
https://github.com/CVHub520/X-AnyLabeling

---

写给自己的提醒：打开哪个文件夹就会在哪个文件夹下生成runs