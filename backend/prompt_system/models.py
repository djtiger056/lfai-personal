"""提示词系统数据模型"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class PromptChangeRecord(BaseModel):
    """提示词变更记录"""
    timestamp: str = Field(description="变更时间 ISO 格式")
    source: str = Field(description="变更来源: user / ai / system / migration")
    summary: str = Field(default="", description="变更摘要")
    previous_length: int = Field(default=0, description="变更前提示词字符数")
    new_length: int = Field(default=0, description="变更后提示词字符数")


class PromptData(BaseModel):
    """用户提示词数据"""
    content: str = Field(default="", description="提示词内容")
    updated_at: Optional[str] = Field(default=None, description="最后更新时间")
    source: str = Field(default="system", description="最后修改来源")


class PromptHistory(BaseModel):
    """提示词变更历史"""
    records: List[PromptChangeRecord] = Field(default_factory=list)
