import os
import random
import shutil

# 定义源文件夹，这里假设所有图片都在这个文件夹里喵
source_folder = R'D:\Py-code\yolo\photos' # <--- 请把这里替换成图片文件夹路径

# 定义训练集和测试集的输出文件夹
train_folder = R'D:\Py-code\yolo\photos\train' # <--- 训练集输出路径
test_folder = R'D:\Py-code\yolo\photos\test'   # <--- 测试集输出路径

# 确保输出文件夹存在，如果不存在就创建它们喵
os.makedirs(train_folder, exist_ok=True)
os.makedirs(test_folder, exist_ok=True)

# 获取所有图片文件的列表喵
image_files = [f for f in os.listdir(source_folder) if os.path.isfile(os.path.join(source_folder, f))]

# 随机打乱文件列表，这样可以保证训练集和测试集的随机性喵
random.shuffle(image_files)

# 计算80%作为训练集，20%作为测试集喵
total_images = len(image_files)
train_split_index = int(total_images * 0.8)

# 分割文件列表喵
train_files = image_files[:train_split_index]
test_files = image_files[train_split_index:]

print(f'总共有 {total_images} 张图片喵。')
print(f'将会有 {len(train_files)} 张图片用于训练喵。')
print(f'将会有 {len(test_files)} 张图片用于测试喵。')

# 将文件复制到对应的文件夹喵
print('\n正在复制训练集文件喵...')
for filename in train_files:
    source_path = os.path.join(source_folder, filename)
    destination_path = os.path.join(train_folder, filename)
    shutil.copy(source_path, destination_path)
    # print(f'复制 {filename} 到训练集喵') # 如果文件太多，打印会比较慢，可以注释掉
print('训练集文件复制完成喵！')

print('\n正在复制测试集文件喵...')
for filename in test_files:
    source_path = os.path.join(source_folder, filename)
    destination_path = os.path.join(test_folder, filename)
    shutil.copy(source_path, destination_path)
    # print(f'复制 {filename} 到测试集喵') # 如果文件太多，打印会比较慢，可以注释掉
print('测试集文件复制完成喵！')
print('\n数据集分割完成啦喵！现在你可以用这些数据来训练你的模型了喵！(๑•̀ㅂ•́)و✧')