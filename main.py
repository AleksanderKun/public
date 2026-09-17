import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LinkJob AI")
        self.setGeometry(100, 100, 800, 600)

        label = QLabel("Witaj w aplikacji LinkJob AI!", self)
        label.setGeometry(100, 100, 600, 100)
        label.setStyleSheet("font-size: 24px;")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
