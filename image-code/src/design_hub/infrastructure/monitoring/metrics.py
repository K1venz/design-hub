"""出图业务 Prometheus 指标定义（PRD §6.3.5）。

模块级单例注册到默认 REGISTRY；instrumentator 的 /metrics 会一并暴露。
HTTP/系统指标(QPS/时延/状态码)由 instrumentator 自动采集，不在此处。
"""

from prometheus_client import Counter, Histogram

GENERATIONS = Counter(
    "design_hub_generations_total",
    "出图任务次数",
    ["model", "mode"],
)
IMAGES = Counter(
    "design_hub_images_generated_total",
    "出图候选张数",
    ["model"],
)
COST = Counter(
    "design_hub_generation_cost_cny_total",
    "出图累计成本(元)",
    ["model"],
)
LATENCY = Histogram(
    "design_hub_generation_latency_seconds",
    "单次出图时延(秒)",
    ["model"],
)
