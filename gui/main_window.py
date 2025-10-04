from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QStatusBar
from gui.plot_widget import PPGPlotWidget

class MainWindow(QMainWindow):
    def __init__(self, worker):
        super().__init__()
        self.setWindowTitle("手表实时PPG监测")

        # 中央控件
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # PPG 波形控件
        self.plot_widget = PPGPlotWidget(fs=100, display_sec=6)
        self.layout.addWidget(self.plot_widget)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("等待连接...")

        # 关联 Worker 信号
        self.worker = worker
        self.worker.ppg_signal.connect(self.plot_widget.update_data)
        self.worker.status_signal.connect(self.update_status)
        self.worker.hr_signal.connect(self.update_hr)
        self.worker.start()

    # 状态栏更新
    def update_status(self, msg: str):
        self.status_bar.showMessage(msg)

    def update_hr(self, bpm):
        self.status_bar.showMessage(f"心率: {bpm:.1f} BPM")

    # 窗口大小变化事件，保持波形控件16:9
    def resizeEvent(self, event):
        # 获取可用尺寸
        w = self.central.width()
        h = self.central.height()
        # 16:9 宽高比例
        target_ratio = 16 / 9
        if w / h > target_ratio:
            # 窗口太宽，限制宽度
            new_w = int(h * target_ratio)
            new_h = h
        else:
            # 窗口太高，限制高度
            new_w = w
            new_h = int(w / target_ratio)

        # 调整波形控件尺寸，保持比例
        self.plot_widget.setFixedSize(new_w, new_h)
        
        super().resizeEvent(event)

    # 窗口关闭时停止 worker
    def closeEvent(self, event):
        """
        安全关闭：
        1. 停止 Worker 的运行循环
        2. 等待 Worker 完全退出
        3. 然后再关闭窗口
        """
        if self.worker.isRunning():
            self.worker.running = False  # 停止循环
            # 停止 asyncio loop 并断开蓝牙
            if self.worker.loop and self.worker.loop.is_running():
                try:
                    self.worker.loop.call_soon_threadsafe(self.worker.loop.stop)
                except Exception:
                    pass
            # 等待线程退出
            self.worker.quit()
            self.worker.wait()
        event.accept()
