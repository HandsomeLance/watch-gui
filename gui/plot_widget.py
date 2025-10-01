from PyQt5.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

class PPGPlotWidget(QWidget):
    def __init__(self):
        super().__init__()
        # 添加字体配置，支持中文显示
        plt.rcParams["font.family"] = ["SimHei"]  # 字体列表
        plt.rcParams["axes.unicode_minus"] = False
        layout = QVBoxLayout(self)
        self.fig, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)
        self.buffer = []

    def update_data(self, new_points):
        self.buffer = new_points
        self.ax.clear()
        self.ax.plot(self.buffer, color='g')
        self.ax.set_title("预处理后的实时 PPG")
        self.canvas.draw()
