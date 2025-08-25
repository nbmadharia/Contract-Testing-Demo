import requests, json

class OllamaClient:
    def __init__(self, ollama_cfg: dict):
        self.base = ollama_cfg["base_url"].rstrip("/")
        self.models = {
            "planner_model": ollama_cfg["planner_model"],
            "coder_model": ollama_cfg["coder_model"],
            "critic_model": ollama_cfg.get("critic_model", ollama_cfg["planner_model"])
        }

    def complete(self, which: str, prompt: str) -> str:
        model = self.models[which]
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": 8192, "temperature": 0.2}
        }
        r = requests.post(f"{self.base}/api/generate", json=payload, timeout=600)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "")
