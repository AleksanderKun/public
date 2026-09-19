from PyQt5.QtCore import QThread, pyqtSignal
import requests


class ApiWorker(QThread):
    response_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, prompt: str, config):
        super().__init__()
        self.prompt = prompt
        self.config = config

    def run(self):
        url = f"{self.config.api_base}/api/generate"
        payload = {
            "model": self.config.model,
            "prompt": self.prompt,
            "stream": False,
            "options": {"num_ctx": self.config.context_length},
        }
        try:
            response = requests.post(url, json=payload, timeout=self.config.timeout)
            response.raise_for_status()
            response_data = response.json()
            self.response_signal.emit(response_data.get("output", "Brak odpowiedzi"))
        except requests.RequestException as e:
            self.error_signal.emit(f"Wystąpił błąd podczas komunikacji z API: {e}")
        except Exception as e:
            self.error_signal.emit(f"Wystąpił nieoczekiwany błąd: {e}")
