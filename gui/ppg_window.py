from PyQt5.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QPushButton, QStatusBar
from gui.widget.plot_widget import PPGPlotWidget

class PPGWindow(QMainWindow):
    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self.setWindowTitle("实时PPG波形")
        self.setGeometry(200, 100, 800, 450)

        # 中央控件布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 返回按钮
        self.back_button = QPushButton("返回主菜单")
        self.back_button.clicked.connect(self.go_back)
        layout.addWidget(self.back_button)

        # 波形绘制控件
        self.plot_widget = PPGPlotWidget(fs=100, display_sec=6)
        layout.addWidget(self.plot_widget)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 绑定 Worker 信号
        self.worker = worker
        self.worker.ppg_signal.connect(self.plot_widget.update_data)
        self.worker.hr_signal.connect(self.update_hr)

    def go_back(self):
        """返回主菜单"""
        self.hide()
        if self.parent():
            self.parent().show()  # 显示主窗口

    def update_hr(self, bpm):
        self.status_bar.showMessage(f"心率: {bpm:.1f} BPM")
