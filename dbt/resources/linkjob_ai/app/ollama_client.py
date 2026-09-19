import requests
from .config import Config


class OllamaClient:
    def __init__(self, config: Config):
        self.config = config

    def generate(self, prompt: str) -> str:
        url = f"{self.config.api_base}/api/generate"
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": self.config.context_length},
        }
        try:
            response = requests.post(url, json=payload, timeout=self.config.timeout)
            response.raise_for_status()
            response_data = response.json()
            return response_data.get("output", "Brak odpowiedzi")
        except requests.RequestException as e:
            raise Exception(f"Wystąpił błąd podczas komunikacji z API: {e}")
        except Exception as e:
            raise Exception(f"Wystąpił nieoczekiwany błąd: {e}")
