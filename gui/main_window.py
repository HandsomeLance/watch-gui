from PyQt5.QtWidgets import QMainWindow, QWidget, QStackedLayout, QStatusBar
from gui.widget.connect_widget import ConnectWidget
from gui.widget.menu_widget import MenuWidget
from gui.ppg_window import PPGWindow
from PyQt5.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self, worker):
        super().__init__()
        self.setWindowTitle("手表实时PPG监测")
        # 窗口大小设置
        self.resize(400, 300)

        # 中央堆叠布局（连接界面 + 菜单界面）
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.stack = QStackedLayout(self.central)

        # 两个主界面
        self.connect_widget = ConnectWidget()
        self.menu_widget = MenuWidget()

        self.stack.addWidget(self.connect_widget)
        self.stack.addWidget(self.menu_widget)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 蓝牙 Worker 信号
        self.worker = worker
        self.worker.status_signal.connect(self.update_status)
        self.worker.start()

        # 按钮信号
        self.menu_widget.open_plot_signal.connect(self.open_ppg_window)

        # 初始显示连接界面
        self.show_connect_page()

        # 记录波形窗口实例
        self.ppg_window = None

    # 界面切换
    def show_connect_page(self):
        self.stack.setCurrentWidget(self.connect_widget)
        self.connect_widget.set_message("正在连接手表...")

    def show_menu_page(self):
        self.stack.setCurrentWidget(self.menu_widget)
        self.status_bar.showMessage("手表已连接成功")

    # 打开波形窗口
    def open_ppg_window(self):
        if self.ppg_window is None:
            self.ppg_window = PPGWindow(self.worker, parent=self)
        self.ppg_window.show()
        self.hide()  # 隐藏主窗口

    # 状态栏更新
    def update_status(self, msg: str):
        self.status_bar.showMessage(msg)
        if "连接成功" in msg:
            self.show_menu_page()
        elif "连接" in msg and "失败" not in msg:
            self.connect_widget.set_message(msg)

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
