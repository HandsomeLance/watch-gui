# gui/menu_widget.py
from PyQt5.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

class MenuWidget(QWidget):
    """连接成功后出现的菜单界面"""
    open_plot_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("手表已连接成功！")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        btn1 = QPushButton("查看实时PPG波形")
        btn2 = QPushButton("功能二（开发中）")
        btn3 = QPushButton("功能三（开发中）")

        btn1.clicked.connect(self.open_plot_signal.emit)

        for b in [btn1, btn2, btn3]:
            b.setFixedWidth(200)
            layout.addWidget(b, alignment=Qt.AlignCenter)

        self.setLayout(layout)