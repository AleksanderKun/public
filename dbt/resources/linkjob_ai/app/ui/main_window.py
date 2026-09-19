from PyQt5.QtWidgets import QMainWindow, QVBoxLayout, QWidget
from .chat_window import ChatWindow
from ..config import Config


class MainWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("LinkJob AI")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        self.chat_window = ChatWindow(self.config)
        layout.addWidget(self.chat_window)
