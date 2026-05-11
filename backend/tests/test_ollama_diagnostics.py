from app.services.ollama_diagnostics import (
    cpu_evidence_from_logs,
    find_embedding_context_errors,
    gpu_evidence_from_logs,
    parse_ollama_ps,
)


def test_parse_ollama_ps_detects_gpu_processor():
    output = """
NAME                     ID              SIZE      PROCESSOR    CONTEXT    UNTIL
embeddinggemma:latest    85462619ee72    1.1 GB    100% GPU     2048       4 minutes from now
"""

    processor = parse_ollama_ps(output, "embeddinggemma")

    assert processor is not None
    assert processor.processor == "100% GPU"
    assert processor.uses_gpu
    assert not processor.uses_cpu


def test_parse_ollama_ps_detects_cpu_processor():
    output = """
NAME                     ID              SIZE      PROCESSOR    CONTEXT    UNTIL
embeddinggemma:latest    85462619ee72    1.1 GB    100% CPU     2048       4 minutes from now
"""

    processor = parse_ollama_ps(output, "embeddinggemma")

    assert processor is not None
    assert processor.uses_cpu
    assert not processor.uses_gpu


def test_parse_ollama_ps_matches_model_without_latest_tag():
    output = """
NAME                     ID              SIZE      PROCESSOR    CONTEXT    UNTIL
embeddinggemma:latest    85462619ee72    1.1 GB    100% GPU     2048       4 minutes from now
"""

    assert parse_ollama_ps(output, "embeddinggemma") is not None
    assert parse_ollama_ps(output, "different-model") is None


def test_find_embedding_context_errors_from_ollama_logs():
    logs = """
ollama-1  | [GIN] 2026/05/11 - 03:17:18 | 200 | 825ms | POST "/api/embed"
ollama-1  | time=2026-05-11T03:17:23.555Z level=INFO source=server.go:1795 msg="llm embedding error: the input length exceeds the context length"
ollama-1  | [GIN] 2026/05/11 - 03:17:24 | 200 | 1.5s | POST "/api/embed"
"""

    errors = find_embedding_context_errors(logs)

    assert len(errors) == 1
    assert "input length exceeds the context length" in errors[0]


def test_gpu_evidence_from_ollama_logs():
    logs = """
ollama-1  | time=2026-05-11T03:11:54.021Z level=INFO source=sched.go:491 msg="gpu memory" id=GPU-abbb62f2 library=CUDA
ollama-1  | ggml_cuda_init: found 1 CUDA devices:
ollama-1  | load_backend: loaded CUDA backend from /usr/lib/ollama/cuda_v12/libggml-cuda.so
ollama-1  | time=2026-05-11T03:11:54.694Z level=INFO source=ggml.go:502 msg="offloaded 25/25 layers to GPU"
"""

    evidence = gpu_evidence_from_logs(logs)

    assert len(evidence) == 4
    assert cpu_evidence_from_logs(logs) == []


def test_cpu_evidence_from_ollama_logs():
    logs = """
ollama-1  | time=2026-05-11T03:11:54.021Z level=WARN source=gpu.go:111 msg="no compatible GPUs were discovered"
ollama-1  | time=2026-05-11T03:11:54.694Z level=INFO source=ggml.go:502 msg="offloaded 0/25 layers to GPU"
"""

    evidence = cpu_evidence_from_logs(logs)

    assert len(evidence) == 2
    assert gpu_evidence_from_logs(logs) == []
