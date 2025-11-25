# split_voices_npy.py
import numpy as np
from pathlib import Path

src = Path('voices-v1.1-zh.bin')   # 原 npz
out_dir = Path('single_voices')
out_dir.mkdir(exist_ok=True)

voices = np.load(src)
for name in voices.keys():
    np.save(out_dir / f'{name}.npy', voices[name])   # 裸 .npy
    print(f'saved  {name}.npy')

print('全部拆完 ✅', len(voices), '个文件在', out_dir)