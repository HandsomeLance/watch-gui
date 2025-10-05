# gui/main_window.py
from PyQt5.QtWidgets import QMainWindow, QWidget, QStackedLayout, QStatusBar
from gui.connect_widget import ConnectWidget
from gui.menu_widget import MenuWidget
from gui.plot_widget import PPGPlotWidget

class MainWindow(QMainWindow):
    def __init__(self, worker):
        super().__init__()
        self.setWindowTitle("手表实时PPG监测")

        # 中央堆叠布局（多个界面切换）
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.stack = QStackedLayout(self.central)

        # 三个界面
        self.connect_widget = ConnectWidget()
        self.menu_widget = MenuWidget()
        self.plot_widget = PPGPlotWidget(fs=100, display_sec=6)

        self.stack.addWidget(self.connect_widget)
        self.stack.addWidget(self.menu_widget)
        self.stack.addWidget(self.plot_widget)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Worker 信号
        self.worker = worker
        self.worker.status_signal.connect(self.update_status)
        self.worker.ppg_signal.connect(self.plot_widget.update_data)
        self.worker.hr_signal.connect(self.update_hr)
        self.worker.start()

        # 按钮切换信号
        self.menu_widget.open_plot_signal.connect(self.show_plot_page)

        # 初始显示连接界面
        self.show_connect_page()

    # 切换界面
    def show_connect_page(self):
        self.stack.setCurrentWidget(self.connect_widget)
        self.connect_widget.set_message("正在连接手表...")

    def show_menu_page(self):
        self.stack.setCurrentWidget(self.menu_widget)
        self.status_bar.showMessage("手表已连接成功")

    def show_plot_page(self):
        self.stack.setCurrentWidget(self.plot_widget)
        self.status_bar.showMessage("正在显示实时PPG波形")

    # 状态栏更新
    def update_status(self, msg: str):
        self.status_bar.showMessage(msg)
        if "连接成功" in msg:
            self.show_menu_page()
        elif "连接" in msg and "失败" not in msg:
            self.connect_widget.set_message(msg)

    def update_hr(self, bpm):
        self.status_bar.showMessage(f"心率: {bpm:.1f} BPM")

    def closeEvent(self, event):
        """安全关闭"""
        if self.worker.isRunning():
            self.worker.running = False
            if self.worker.loop and self.worker.loop.is_running():
                try:
                    self.worker.loop.call_soon_threadsafe(self.worker.loop.stop)
                except Exception:
                    pass
            self.worker.quit()
            self.worker.wait()
        event.accept()
