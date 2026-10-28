"""Explainable rules behind a replaceable interface. This is NOT a trained model."""
from dataclasses import dataclass, asdict
from typing import Protocol

@dataclass(frozen=True)
class EmotionState:
    label: str
    reason: str
    source: str = "keyword_rules_v1"
    trained_model: bool = False

    def as_dict(self):
        return asdict(self)

class EmotionProvider(Protocol):
    def infer(self, text: str) -> EmotionState: ...

class RuleEmotion:
    def infer(self, text):
        for label, words in (
            ("需要支持", ("难过", "焦虑", "累", "烦", "伤心")),
            ("积极", ("开心", "高兴", "谢谢", "太好了")),
        ):
            matched = [word for word in words if word in text]
            if matched:
                return EmotionState(label, "命中关键词：" + "、".join(matched))
        return EmotionState("中性", "没有命中情绪关键词；仅作界面状态参考。")