"""
Keyword taxonomy for applied AI executive positioning.

Organized by domain with priority weights for production-focused content filtering.
"""

from dataclasses import dataclass, field
from enum import Enum


class KeywordPriority(Enum):
    HIGH = "high"        # Must appear in 70%+ of surfaced content
    MEDIUM = "medium"    # Nice to have, 30-50%
    LOW = "low"          # Supplementary, <20%


@dataclass(frozen=True)
class KeywordCategory:
    name: str
    keywords: tuple[str, ...]
    priority: KeywordPriority
    description: str = ""


# ---------------------------------------------------------------------------
# Core ML/AI Domains (Foundational)
# ---------------------------------------------------------------------------
CORE_ML_AI = KeywordCategory(
    name="Core ML/AI Domains",
    description="Foundational machine learning and AI terminology",
    priority=KeywordPriority.MEDIUM,
    keywords=(
        "deep learning", "machine learning", "artificial intelligence",
        "neural networks", "computer vision", "natural language processing",
        "NLP", "speech recognition", "reinforcement learning",
        "self-supervised learning", "semi-supervised learning",
        "multimodal learning", "vision-language models", "VLMs",
    ),
)

# ---------------------------------------------------------------------------
# Frameworks & Tools
# ---------------------------------------------------------------------------
FRAMEWORKS_TOOLS = KeywordCategory(
    name="Frameworks & Tools",
    description="Hands-on expertise in ML/AI frameworks",
    priority=KeywordPriority.HIGH,
    keywords=(
        "PyTorch", "TensorFlow", "JAX", "Keras", "scikit-learn",
        "ONNX", "TensorRT", "OpenVINO", "TorchScript",
        "Hugging Face", "transformers", "diffusers", "accelerate",
        "LangChain", "LlamaIndex", "LangGraph", "Semantic Kernel",
        "Ray", "Dask", "Spark MLlib", "Horovod",
    ),
)

# ---------------------------------------------------------------------------
# LLM & Generative AI
# ---------------------------------------------------------------------------
LLM_GENAI = KeywordCategory(
    name="LLM & Generative AI",
    description="Trending, high-visibility LLM and generative AI topics",
    priority=KeywordPriority.HIGH,
    keywords=(
        "large language models", "LLMs", "foundation models", "frontier models",
        "GPT", "Claude", "Llama", "Mistral", "Gemini", "open weight models",
        "retrieval augmented generation", "RAG", "vector search", "semantic search",
        "prompt engineering", "few-shot learning", "in-context learning",
        "fine-tuning", "LoRA", "QLoRA", "PEFT", "parameter-efficient fine-tuning",
        "instruction tuning", "RLHF", "constitutional AI", "alignment",
        "diffusion models", "stable diffusion", "text-to-image",
        "generative AI", "GenAI",
        "multimodal models", "vision transformers", "ViT", "CLIP", "BLIP",
    ),
)

# ---------------------------------------------------------------------------
# Production & Deployment
# ---------------------------------------------------------------------------
PRODUCTION_DEPLOYMENT = KeywordCategory(
    name="Production & Deployment",
    description="AI in production at scale - critical for executive positioning",
    priority=KeywordPriority.HIGH,
    keywords=(
        "model deployment", "production ML", "AI in production", "AI at scale",
        "inference optimization", "model serving", "online inference", "batch inference",
        "model compression", "quantization", "pruning", "knowledge distillation",
        "int8", "fp16", "bfloat16", "mixed precision training",
        "edge AI", "edge deployment", "on-device ML", "TinyML",
        "model monitoring", "drift detection", "model performance tracking",
        "A/B testing", "shadow deployment", "canary deployment",
        "blue-green deployment",
    ),
)

# ---------------------------------------------------------------------------
# Infrastructure & Operations
# ---------------------------------------------------------------------------
INFRASTRUCTURE_OPS = KeywordCategory(
    name="Infrastructure & Operations",
    description="Executive/architectural thinking about ML infrastructure",
    priority=KeywordPriority.HIGH,
    keywords=(
        "MLOps", "LLMOps", "AI operations", "ML infrastructure", "AI infrastructure",
        "feature stores", "data pipelines", "data versioning", "DVC",
        "experiment tracking", "model registry", "artifact management",
        "distributed training", "data parallelism", "model parallelism",
        "pipeline parallelism",
        "GPU optimization", "CUDA", "cuDNN", "tensor cores", "NVIDIA", "AMD ROCm",
        "Kubernetes", "Docker", "containerization", "orchestration",
        "cloud AI", "AWS SageMaker", "Azure ML", "Google Vertex AI", "Databricks",
        "cost optimization", "GPU utilization", "compute efficiency", "FinOps for ML",
    ),
)

# ---------------------------------------------------------------------------
# Data & Vector Technologies
# ---------------------------------------------------------------------------
DATA_VECTOR = KeywordCategory(
    name="Data & Vector Technologies",
    description="RAG/LLM ecosystem data technologies",
    priority=KeywordPriority.MEDIUM,
    keywords=(
        "vector databases", "embeddings", "semantic embeddings",
        "Pinecone", "Weaviate", "Milvus", "Chroma", "Qdrant", "FAISS",
        "data preprocessing", "data quality", "synthetic data", "data augmentation",
    ),
)

# ---------------------------------------------------------------------------
# Emerging Technologies
# ---------------------------------------------------------------------------
EMERGING_TECH = KeywordCategory(
    name="Emerging Technologies",
    description="Forward-thinking positioning in emerging AI areas",
    priority=KeywordPriority.MEDIUM,
    keywords=(
        "agentic AI", "AI agents", "autonomous agents", "multi-agent systems",
        "AutoGen", "CrewAI", "agent frameworks", "tool-using agents",
        "vLLM", "text-generation-inference", "TGI", "inference servers",
        "mixture of experts", "MoE", "sparse models", "efficient architectures",
        "open source AI", "open models", "model transparency", "responsible AI",
        "AI governance", "model cards", "fairness", "bias mitigation",
        "explainability",
    ),
)

# ---------------------------------------------------------------------------
# Business & Strategy
# ---------------------------------------------------------------------------
BUSINESS_STRATEGY = KeywordCategory(
    name="Business & Strategy",
    description="Executive perspective on AI strategy and transformation",
    priority=KeywordPriority.LOW,
    keywords=(
        "AI strategy", "AI transformation", "AI ROI", "business value of AI",
        "build vs buy", "vendor selection", "AI procurement",
        "AI team building", "talent acquisition", "upskilling",
        "AI ethics", "AI regulation", "AI compliance", "GDPR", "AI Act",
    ),
)

# ---------------------------------------------------------------------------
# All categories
# ---------------------------------------------------------------------------
ALL_CATEGORIES: list[KeywordCategory] = [
    CORE_ML_AI,
    FRAMEWORKS_TOOLS,
    LLM_GENAI,
    PRODUCTION_DEPLOYMENT,
    INFRASTRUCTURE_OPS,
    DATA_VECTOR,
    EMERGING_TECH,
    BUSINESS_STRATEGY,
]

# ---------------------------------------------------------------------------
# Flat keyword sets by priority for quick lookup
# ---------------------------------------------------------------------------
HIGH_PRIORITY_KEYWORDS: set[str] = set()
MEDIUM_PRIORITY_KEYWORDS: set[str] = set()
LOW_PRIORITY_KEYWORDS: set[str] = set()

for _cat in ALL_CATEGORIES:
    _target = {
        KeywordPriority.HIGH: HIGH_PRIORITY_KEYWORDS,
        KeywordPriority.MEDIUM: MEDIUM_PRIORITY_KEYWORDS,
        KeywordPriority.LOW: LOW_PRIORITY_KEYWORDS,
    }[_cat.priority]
    _target.update(_cat.keywords)

ALL_KEYWORDS: set[str] = HIGH_PRIORITY_KEYWORDS | MEDIUM_PRIORITY_KEYWORDS | LOW_PRIORITY_KEYWORDS

# ---------------------------------------------------------------------------
# Production scoring keywords with weights (used by content_filter.py)
# ---------------------------------------------------------------------------
PRODUCTION_KEYWORDS: dict[str, int] = {
    "production": 10, "deployment": 10, "at scale": 12,
    "infrastructure": 8, "MLOps": 10, "LLMOps": 10,
    "serving": 8, "inference": 8, "optimization": 7,
    "performance": 6, "latency": 7, "throughput": 7,
    "real-world": 9, "case study": 11, "implementation": 9,
    "model deployment": 12, "production ML": 12,
    "AI in production": 14, "AI at scale": 14,
    "model serving": 10, "inference optimization": 12,
    "distributed training": 10, "GPU optimization": 10,
}

RESEARCH_KEYWORDS: dict[str, int] = {
    "paper": 3, "research": 3, "novel": 2, "proposed": 2,
    "state-of-the-art": 4, "benchmark": 5, "experiment": 3,
    "sota": 4, "ablation": 2,
}

BUSINESS_KEYWORDS: dict[str, int] = {
    "ROI": 8, "cost": 7, "efficiency": 7, "business value": 9,
    "enterprise": 8, "scalability": 9, "reliability": 8,
    "revenue": 7, "profit": 6, "competitive advantage": 8,
}

IMPLEMENTATION_KEYWORDS: dict[str, int] = {
    "code": 6, "GitHub": 7, "open source": 7, "tutorial": 5,
    "how to": 6, "best practices": 8, "guide": 6, "framework": 7,
    "repository": 5, "library": 5, "SDK": 6, "API": 5,
}

EXECUTIVE_SCALE_INDICATORS: list[str] = [
    "distributed", "large-scale", "thousands of", "millions of",
    "enterprise-wide", "organization-wide", "company-wide",
    "petabyte", "terabyte", "cluster", "fleet",
]

EXECUTIVE_LEADERSHIP_SIGNALS: list[str] = [
    "architecture", "strategy", "decision", "trade-offs", "trade-off",
    "evaluation", "assessment", "recommendation", "roadmap",
    "technical leadership", "engineering leadership",
]

EXECUTIVE_OPERATIONAL_EXCELLENCE: list[str] = [
    "monitoring", "observability", "incident", "postmortem",
    "lessons learned", "retrospective", "on-call", "SLA", "SLO",
    "uptime", "availability", "resilience",
]

EXECUTIVE_TEAM_ORG: list[str] = [
    "team", "process", "workflow", "collaboration", "cross-functional",
    "hiring", "onboarding", "culture", "management",
]

THEORY_ONLY_INDICATORS: list[str] = [
    "theoretical", "abstract", "mathematical proof", "theorem",
    "lemma", "corollary", "purely theoretical",
]
