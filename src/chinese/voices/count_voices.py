# count_voices.py
import numpy as np

f = np.load('voices-v1.1-zh.bin')   # 虽然后缀是 .bin，其实是 npz
print('说话人总数:', len(f))
print('key 列表:', list(f.keys()))   # 想细看就打印