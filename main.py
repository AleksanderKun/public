import sys
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QLabel,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LinkJob AI")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        self.text_edit = QTextEdit(self)
        layout.addWidget(self.text_edit)

        self.start_button = QPushButton("Rozpocznij", self)
        self.start_button.clicked.connect(self.start_processing)
        layout.addWidget(self.start_button)

        self.status_label = QLabel("Status: Oczekiwanie", self)
        layout.addWidget(self.status_label)

    def start_processing(self):
        # Tutaj dodaj kod przetwarzania danych
        input_data = self.text_edit.toPlainText()
        # Przykładowa logika przetwarzania
        processed_data = f"Przetworzone dane: {input_data}"
        self.status_label.setText("Status: Zakończone")
        self.text_edit.append(processed_data)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
