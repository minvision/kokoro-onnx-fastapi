# bin2npy_no_voices.py
import numpy as np
import os

bin_file = 'voices-v1.1-zh.bin'
npy_file = 'voices-v1.1-zh.npy'

# 1. 读裸二进制
vec = np.fromfile(bin_file, dtype=np.float32)

# 2. 反推说话人数
bytes_per_speaker = 256 * 4          # 256 维 float32
n_speakers = vec.size // 256
assert vec.size % 256 == 0, f"文件大小不是 256 的整数倍，可能不是标准 voices 文件"

vec = vec.reshape(n_speakers, 256)
print('speakers:', n_speakers, 'shape:', vec.shape)

# 3. 保存
np.save(npy_file, vec)
print('已写入', npy_file)