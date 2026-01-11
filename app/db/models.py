from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
import uuid
from datetime import datetime

Base = declarative_base()

class IntelligenceSource(Base):
    __tablename__ = "intelligence_sources"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(String, nullable=False)
    status = Column(String, default="active")  # active, inactive, error
    last_crawled_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("IntelligenceItem", back_populates="source")

class IntelligenceItem(Base):
    __tablename__ = "intelligence_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String, ForeignKey("intelligence_sources.id"))
    url = Column(Text, nullable=True) # Specific article URL
    
    title = Column(String, nullable=True)
    title_zh = Column(String, nullable=True)  # 中文标题
    publish_date = Column(String, nullable=True) # Keep as string for flexibility parsing
    content_type = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    risk_tags = Column(JSON, nullable=True)
    risk_hint = Column(Text, nullable=True)
    original_text = Column(Text, nullable=True)
    translated_text = Column(Text, nullable=True)
    relevance_score = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    source = relationship("IntelligenceSource", back_populates="items")

class ContractTask(Base):
    __tablename__ = "contract_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="processing") # processing, done, failed
    overall_risk_level = Column(String, nullable=True) # High, Medium, Low
    
    risks = relationship("ContractRisk", back_populates="task")

class ContractRisk(Base):
    __tablename__ = "contract_risks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String, ForeignKey("contract_tasks.id"))
    
    clause_id = Column(String, nullable=True)
    clause_text = Column(Text, nullable=True)
    risk_category = Column(String, nullable=True)
    risk_level = Column(String, nullable=True)
    risk_reason = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)

    task = relationship("ContractTask", back_populates="risks")
