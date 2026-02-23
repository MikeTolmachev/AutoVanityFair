"""
Keyword taxonomy for applied AI executive positioning.

Organized by domain with priority weights for business-applied,
production-focused content filtering. PyTorch-centric; TensorFlow
is treated as legacy/low-priority.
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
# Frameworks & Tools (PyTorch-centric, TensorFlow demoted)
# ---------------------------------------------------------------------------
FRAMEWORKS_TOOLS = KeywordCategory(
    name="Frameworks & Tools",
    description="Hands-on expertise -- PyTorch ecosystem is primary",
    priority=KeywordPriority.HIGH,
    keywords=(
        "PyTorch", "JAX", "scikit-learn",
        "ONNX", "TensorRT", "OpenVINO", "TorchScript",
        "Hugging Face", "transformers", "diffusers", "accelerate",
        "LangChain", "LlamaIndex", "LangGraph", "Semantic Kernel",
        "Ray", "Dask",
    ),
)

# TensorFlow / Keras split out as low-priority (legacy)
LEGACY_FRAMEWORKS = KeywordCategory(
    name="Legacy Frameworks",
    description="Declining frameworks -- kept for completeness but low weight",
    priority=KeywordPriority.LOW,
    keywords=(
        "TensorFlow", "Keras", "TFX", "TensorFlow Serving",
        "Spark MLlib", "Horovod",
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
    description="AI in production at scale -- business outcomes focus",
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
# Infrastructure & Operations (rebalanced: less DevOps, more outcomes)
# ---------------------------------------------------------------------------
INFRASTRUCTURE_OPS = KeywordCategory(
    name="Infrastructure & Operations",
    description="ML infrastructure with business-outcome lens",
    priority=KeywordPriority.MEDIUM,
    keywords=(
        "MLOps", "LLMOps", "AI operations", "ML infrastructure", "AI infrastructure",
        "feature stores", "data pipelines", "data versioning",
        "experiment tracking", "model registry",
        "distributed training", "data parallelism", "model parallelism",
        "GPU optimization", "CUDA", "NVIDIA",
        "cloud AI", "AWS SageMaker", "Azure ML", "Google Vertex AI", "Databricks",
        "cost optimization", "compute efficiency", "FinOps for ML",
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
# Business & Strategy (promoted from LOW -> HIGH)
# ---------------------------------------------------------------------------
BUSINESS_STRATEGY = KeywordCategory(
    name="Business & Strategy",
    description="Executive perspective -- business value, ROI, applied outcomes",
    priority=KeywordPriority.HIGH,
    keywords=(
        "AI strategy", "AI transformation", "AI ROI", "business value of AI",
        "build vs buy", "vendor selection", "AI procurement",
        "AI team building", "talent acquisition", "upskilling",
        "AI ethics", "AI regulation", "AI compliance", "GDPR", "AI Act",
        "time to market", "product-market fit", "customer experience",
        "AI-powered product", "AI use case", "business impact",
        "revenue growth", "cost reduction", "operational efficiency",
        "digital transformation", "competitive advantage",
    ),
)

# ---------------------------------------------------------------------------
# All categories
# ---------------------------------------------------------------------------
ALL_CATEGORIES: list[KeywordCategory] = [
    CORE_ML_AI,
    FRAMEWORKS_TOOLS,
    LEGACY_FRAMEWORKS,
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
# Framework-specific weights (PyTorch >> TensorFlow)
# ---------------------------------------------------------------------------
FRAMEWORK_WEIGHTS: dict[str, int] = {
    "PyTorch": 10,
    "JAX": 7,
    "Hugging Face": 9,
    "transformers": 8,
    "ONNX": 6,
    "TensorRT": 7,
    "LangChain": 7,
    "LlamaIndex": 7,
    "Ray": 6,
    # Legacy / declining -- low or negative weight
    "TensorFlow": 2,
    "Keras": 2,
    "TFX": 1,
    "Horovod": 1,
}

# ---------------------------------------------------------------------------
# Production scoring keywords with weights (used by content_filter.py)
# ---------------------------------------------------------------------------
PRODUCTION_KEYWORDS: dict[str, int] = {
    "production": 10, "deployment": 10, "at scale": 12,
    "infrastructure": 6, "MLOps": 7, "LLMOps": 8,
    "serving": 8, "inference": 8, "optimization": 7,
    "performance": 6, "latency": 7, "throughput": 7,
    "real-world": 9, "case study": 11, "implementation": 9,
    "model deployment": 12, "production ML": 12,
    "AI in production": 14, "AI at scale": 14,
    "model serving": 10, "inference optimization": 12,
    "distributed training": 8, "GPU optimization": 8,
}

RESEARCH_KEYWORDS: dict[str, int] = {
    "paper": 3, "research": 3, "novel": 2, "proposed": 2,
    "state-of-the-art": 4, "benchmark": 5, "experiment": 3,
    "sota": 4, "ablation": 2,
}

BUSINESS_KEYWORDS: dict[str, int] = {
    "ROI": 10, "cost": 7, "efficiency": 8, "business value": 12,
    "enterprise": 9, "scalability": 9, "reliability": 8,
    "revenue": 9, "profit": 7, "competitive advantage": 10,
    "customer": 7, "product": 6, "market": 6,
    "time to market": 10, "business impact": 12,
    "cost reduction": 10, "revenue growth": 10,
    "digital transformation": 8, "AI strategy": 10,
    "use case": 8, "operational efficiency": 9,
    "AI-powered": 8, "business outcome": 11,
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
    "CTO", "VP of Engineering", "Head of AI", "Chief AI Officer",
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

EXECUTIVE_BUSINESS_OUTCOMES: list[str] = [
    "revenue impact", "cost savings", "customer satisfaction",
    "time to value", "operational efficiency", "market share",
    "competitive moat", "business case", "stakeholder",
    "board", "C-suite", "executive sponsor",
]

THEORY_ONLY_INDICATORS: list[str] = [
    "theoretical", "abstract", "mathematical proof", "theorem",
    "lemma", "corollary", "purely theoretical",
]
