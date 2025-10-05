import sys
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

from ble.watch_worker import WatchWorker
from signal_processing.rri import RRIProcessor

class RealTimePPGWindow(QMainWindow):
    def __init__(self, device_name="Q31(ID-B4F7)", fs=100):
        super().__init__()
        self.setWindowTitle("实时PPG波形测试")
        self.resize(900, 400)

        # 中央控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # matplotlib canvas
        self.fig, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

        # 初始化
        self.fs = fs
        self.buffer_len = fs * 10  # 显示最近10秒
        self.ppg_buffer = np.zeros(self.buffer_len)
        self.rri_proc = RRIProcessor(fs=self.fs)

        # WatchWorker
        self.worker = WatchWorker(device_name=device_name, fs=fs)
        self.worker.ppg_signal.connect(self.update_ppg)
        self.worker.hr_signal.connect(self.show_hr)
        self.worker.status_signal.connect(self.show_status)
        self.worker.start()

    def update_ppg(self, data):
        """收到 PPG 信号更新图像"""
        data = np.array(data)
        
        # 只取最近 buffer_len 点
        new_data = data[-self.buffer_len:]
        
        # 滚动更新缓冲区
        self.ppg_buffer = np.roll(self.ppg_buffer, -len(new_data))
        self.ppg_buffer[-len(new_data):] = new_data

        # 峰值检测（收缩峰）
        peaks = self.rri_proc.detect_peaks(self.ppg_buffer)

        # 绘图
        self.ax.clear()
        self.ax.plot(self.ppg_buffer, color='g', label='PPG波形')
        if len(peaks) > 0:
            self.ax.plot(peaks, self.ppg_buffer[peaks], 'ro', label='收缩峰')

        # 动态纵坐标，留10%边距
        min_val = np.min(self.ppg_buffer)
        max_val = np.max(self.ppg_buffer)
        margin = (max_val - min_val) * 0.1
        if margin == 0:
            margin = 0.1  # 防止全零情况
        self.ax.set_ylim(min_val - margin, max_val + margin)

        # 坐标标签和标题
        self.ax.set_title("实时PPG波形（红点为检测收缩峰）")
        self.ax.set_xlabel("样本点")
        self.ax.set_ylabel("幅值")
        self.ax.legend(loc='upper right')

        # 刷新画布
        self.canvas.draw()

    def show_hr(self, bpm):
        self.setWindowTitle(f"实时PPG波形测试 - 心率: {bpm:.1f} BPM")

    def show_status(self, msg):
        print(f"[手表状态]: {msg}")

    def closeEvent(self, event):
        """关闭窗口时停止Worker"""
        self.worker.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RealTimePPGWindow()
    window.show()
    sys.exit(app.exec_())
