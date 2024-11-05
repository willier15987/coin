import yfinance as yf
import mplfinance as mpf
import os
import tensorflow as tf
from tensorflow.keras import layers, models
import numpy as np
from PIL import Image

def GetKlineToData():
    # 定义图像和标签的文件夹路径
    image_folder = 'kline_images'
    X = []  # 用来存储图像数据

# 加载所有图像并转换为numpy数组
    for file_name in sorted(os.listdir(image_folder)):
        if file_name.endswith('.png'):
            image_path = os.path.join(image_folder, file_name)
            image = Image.open(image_path).convert('RGB')  # 确保是RGB格式
            image = image.resize((128, 128))  # 调整图像大小为128x128，方便模型处理
            X.append(np.array(image))

# 转换为numpy数组
    X = np.array(X)
    print("图像数据集大小:", X.shape)
    return X

def GetMarkData(labels):
# 转换为numpy数组
    y = np.array(labels)
    print("标签数据大小:", y.shape)
    return y

def SaveNpData(_kline, _markLabels):
    np.save('kline_images_90.npy', _kline)
    np.save('labels_90.npy', _markLabels)

def GetSaveData():
    return np.load('kline_images_90.npy', allow_pickle=True), np.load('labels_90.npy', allow_pickle=True)


doDownLoad = False
if doDownLoad:
    # 获取历史数据，这里以比特币为例
    symbol = 'BTC-USD'  # 这是比特币对美元的交易对
    data = yf.download(symbol, start='2023-01-01', end='2023-02-01', interval='1h')

# 打印数据前几行以确认
    print(data.head())

# 绘制K线图
    mpf.plot(data, type='candle', volume=True, style='charles')

# 保存K线图为图片
    mpf.plot(data, type='candle', volume=True, style='charles', savefig='kline.png')
# 定义保存图像的文件夹
    output_dir = 'kline_images_90'
    os.makedirs(output_dir, exist_ok=True)

# 每5根K线生成一张图
    window_size = 90
    for i in range(window_size, len(data)):
    # 截取固定窗口大小的数据
        subset = data.iloc[i-window_size:i]
        file_name = f'kline_{i}.png'
        file_path = os.path.join(output_dir, file_name)
    
    # 保存K线图
        mpf.plot(subset, type='candle', volume=True, style='charles', savefig=file_path)

        print(f'Saved {file_path}')

    labels = []
    for i in range(window_size, len(data)):
    # 比较当前K线窗口后的一根K线的收盘价变化
        future_close = data.iloc[i]['Close']
        current_close = data.iloc[i - 1]['Close']
    
        label = 1 if future_close > current_close else 0
        labels.append(label)
        print(f'Label for kline_{i}.png: {label}')
        
    markData = np.array(labels)
    SaveNpData(GetKlineToData(), markData)    

# 构建CNN模型
model = models.Sequential()

# 输入层：卷积层+池化层
model.add(layers.Conv2D(32, (3, 3), activation='relu', input_shape=(128, 128, 3)))
model.add(layers.MaxPooling2D((2, 2)))

# 增加几层卷积+池化
model.add(layers.Conv2D(64, (3, 3), activation='relu'))
model.add(layers.MaxPooling2D((2, 2)))

model.add(layers.Conv2D(64, (3, 3), activation='relu'))
model.add(layers.MaxPooling2D((2, 2)))

# 扁平化输出并加全连接层
model.add(layers.Flatten())
model.add(layers.Dense(64, activation='relu'))
model.add(layers.Dense(1, activation='sigmoid'))  # 最后一层输出1或0

# 查看模型架构
model.summary()

# 编译模型
model.compile(optimizer='adam',
              loss='binary_crossentropy',
              metrics=['accuracy'])

# 划分训练集和测试集
from sklearn.model_selection import train_test_split
x, y = GetSaveData()
X_train, X_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=42)

# 训练模型
history = model.fit(X_train, y_train, epochs=10, batch_size=32, validation_data=(X_test, y_test))

# 评估模型
test_loss, test_acc = model.evaluate(X_test, y_test, verbose=2)
print(f'\n测试集准确率: {test_acc}')

# 保存模型
model.save('crypto_price_prediction_model.h5')

# 使用模型进行预测
predictions = model.predict(X_test[:5])
print("前5个测试样本的预测结果:", predictions)
