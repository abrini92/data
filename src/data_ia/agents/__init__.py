"""Scheduler jobs: Orchestrator, Scout, Collector, Controller, Investigator, Strategist."""

from data_ia.agents.base import Agent, AgentResult
from data_ia.agents.collector import CollectorAgent
from data_ia.agents.controller import ControllerAgent
from data_ia.agents.investigator import InvestigatorAgent
from data_ia.agents.orchestrator import OrchestratorAgent
from data_ia.agents.pipeline import run_offline_cycle
from data_ia.agents.scout import ScoutAgent
from data_ia.agents.strategist import StrategistAgent

AGENT_CATALOG = [
    OrchestratorAgent(),
    ScoutAgent(),
    CollectorAgent(),
    ControllerAgent(),
    InvestigatorAgent(),
    StrategistAgent(),
]

__all__ = [
    "AGENT_CATALOG",
    "Agent",
    "AgentResult",
    "CollectorAgent",
    "ControllerAgent",
    "InvestigatorAgent",
    "OrchestratorAgent",
    "ScoutAgent",
    "StrategistAgent",
    "run_offline_cycle",
]
