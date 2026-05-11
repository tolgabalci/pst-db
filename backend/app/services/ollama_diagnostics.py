from dataclasses import dataclass
import re


CONTEXT_LENGTH_ERROR_RE = re.compile(
    r"(llm embedding error:.*input length exceeds.*context length|input length exceeds the context length)",
    re.IGNORECASE,
)
GPU_LOG_RE = re.compile(
    r"(loaded CUDA backend|found \d+ CUDA devices|offloaded (?!0/)\d+/\d+ layers to GPU|device=CUDA|library=CUDA|PROCESSOR\s+.*GPU)",
    re.IGNORECASE,
)
CPU_LOG_RE = re.compile(
    r"(no compatible GPUs|no GPU detected|library=CPU|processor\s+.*CPU|offloaded 0/\d+ layers to GPU)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OllamaProcessor:
    model: str
    processor: str

    @property
    def uses_gpu(self) -> bool:
        return bool(re.search(r"\bGPU\b", self.processor, re.IGNORECASE))

    @property
    def uses_cpu(self) -> bool:
        return bool(re.search(r"\bCPU\b", self.processor, re.IGNORECASE))


def parse_ollama_ps(output: str, model: str | None = None) -> OllamaProcessor | None:
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.upper().startswith("NAME"):
            continue

        parts = re.split(r"\s{2,}", line)
        if len(parts) < 4:
            continue

        name = parts[0]
        if model and not _model_matches(name, model):
            continue
        return OllamaProcessor(model=name, processor=parts[3])
    return None


def find_embedding_context_errors(log_text: str) -> list[str]:
    return [line.strip() for line in log_text.splitlines() if CONTEXT_LENGTH_ERROR_RE.search(line)]


def gpu_evidence_from_logs(log_text: str) -> list[str]:
    return [line.strip() for line in log_text.splitlines() if GPU_LOG_RE.search(line)]


def cpu_evidence_from_logs(log_text: str) -> list[str]:
    return [line.strip() for line in log_text.splitlines() if CPU_LOG_RE.search(line)]


def _model_matches(name: str, expected: str) -> bool:
    expected = expected.strip()
    return name == expected or name == f"{expected}:latest" or name.split(":", 1)[0] == expected.split(":", 1)[0]
