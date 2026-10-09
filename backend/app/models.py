from datetime import datetime
from sqlalchemy import Column, Float, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .db import Base


class Control(Base):
    """One SOC2 (or other framework) checklist item requiring evidence."""
    __tablename__ = "controls"
    id = Column(Integer, primary_key=True)
    framework = Column(String, default="SOC2")
    code = Column(String, index=True)          # e.g. "CC6.1"
    name = Column(String)
    description = Column(Text, default="")
    bindings = relationship("Binding", back_populates="control", cascade="all, delete-orphan")


class Binding(Base):
    """Maps a control to a collector + its config. One control can have many."""
    __tablename__ = "bindings"
    id = Column(Integer, primary_key=True)
    control_id = Column(Integer, ForeignKey("controls.id"))
    collector_type = Column(String)            # registry key, e.g. "http_api"
    config = Column(JSON, default=dict)        # collector-specific params
    schedule_minutes = Column(Integer, default=0)  # 0 = manual only
    control = relationship("Control", back_populates="bindings")
    runs = relationship("Run", back_populates="binding", cascade="all, delete-orphan")


class Run(Base):
    """A single execution of a binding's collector."""
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True)
    binding_id = Column(Integer, ForeignKey("bindings.id"))
    started_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")  # pending|success|error
    message = Column(Text, default="")
    assessment = Column(JSON, default=None)  # AI validator verdict: {satisfied, summary, gaps, confidence}
    binding = relationship("Binding", back_populates="runs")
    evidence = relationship("Evidence", back_populates="run", cascade="all, delete-orphan")


class Evidence(Base):
    """An artifact produced by a run: file on disk + metadata in DB."""
    __tablename__ = "evidence"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"))
    filename = Column(String)
    path = Column(String)                      # on-disk blob path
    sha256 = Column(String)                    # tamper-evidence
    collected_at = Column(DateTime, default=datetime.utcnow)
    meta = Column(JSON, default=dict)
    run = relationship("Run", back_populates="evidence")


class DiscoveryCandidate(Base):
    """A discovered asset proposed as evidence for a control — a *staging* row, not a
    Binding. Keeping it separate means a scan never perturbs the run/schedule path;
    confirming a candidate copies control_id/collector_type/config into a real Binding.
    score + reason + signals are all deterministic and auditable (no LLM confidence)."""
    __tablename__ = "discovery_candidates"
    id = Column(Integer, primary_key=True)
    control_id = Column(Integer, ForeignKey("controls.id"))
    surface = Column(String)                   # documents | cloud | code | web
    source_name = Column(String)               # human label: path, URL, or API descriptor
    collector_type = Column(String)
    config = Column(JSON, default=dict)
    score = Column(Float, default=0.0)
    reason = Column(Text, default="")
    signals = Column(JSON, default=dict)       # matched_terms, ext, age_days, tier
    status = Column(String, default="new")     # new | bound | dismissed
    created_at = Column(DateTime, default=datetime.utcnow)
