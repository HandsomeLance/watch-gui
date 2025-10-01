import numpy as np

def normalize_signal(data, feature_range=(-1, 1)):
    """
    对信号进行归一化
    data: list 或 np.array
    feature_range: 归一化范围，默认 [-1,1]
    返回归一化后的 np.array
    """
    data = np.array(data, dtype=np.float32)
    min_val = np.min(data)
    max_val = np.max(data)
    if max_val - min_val == 0:
        return np.zeros_like(data)
    min_range, max_range = feature_range
    normalized = (data - min_val) / (max_val - min_val)  # 归一化到 [0,1]
    normalized = normalized * (max_range - min_range) + min_range  # 映射到指定范围
    return normalized