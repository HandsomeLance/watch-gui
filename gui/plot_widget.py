from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

class PPGPlotWidget(QWidget):
    def __init__(self, fs=100, display_sec=6):
        super().__init__()
        # 添加字体配置，支持中文显示
        plt.rcParams["font.family"] = ["SimHei"]
        plt.rcParams["axes.unicode_minus"] = False

        layout = QVBoxLayout(self)
        self.fig, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

        self.buffer = []           # 完整缓冲区
        self.fs = fs               # 采样率
        self.display_sec = display_sec  # 显示时长（秒）

    def update_data(self, new_points):
        self.buffer = new_points  # 保留完整缓冲区
        window_size = self.fs * self.display_sec

        # 截取最新 display_sec 秒数据进行绘图
        if len(self.buffer) >= window_size:
            display_data = self.buffer[-window_size:]
        else:
            display_data = self.buffer

        self.ax.clear()
        self.ax.plot(display_data, color='g')
        self.ax.set_title(f"预处理后的实时 PPG（最近 {self.display_sec}s）")
        self.canvas.draw()
