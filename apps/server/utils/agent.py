# ...existing code...
from typing import List

from models.agent import AgentModel
from typings.agent import AgentOutput, AgentWithConfigsOutput, ConfigsOutput
from utils.type import convert_value_to_type
from utils.user import \
    convert_model_to_response as user_convert_model_to_response

import json
import ast
import logging

logger = logging.getLogger(__name__)


def _safe_parse_value(value):
    """
    Return a Python value for JSON/text stored in DB:
    - If already a Python primitive/container, return it.
    - If a string, try json.loads, then ast.literal_eval, otherwise return raw string.
    - None -> None
    """
    if value is None:
        return None
    if isinstance(value, (dict, list, bool, int, float)):
        return value
    if isinstance(value, str):
        # prefer JSON
        try:
            return json.loads(value)
        except Exception:
            try:
                return ast.literal_eval(value)
            except Exception:
                return value
    return str(value)

def convert_model_to_response(agent_model: AgentModel) -> AgentWithConfigsOutput:
    agent_data = {}

    # Extract attributes from AgentModel using annotations of Agent
    for key in AgentOutput.__annotations__.keys():
        if hasattr(agent_model, key):
            target_type = AgentOutput.__annotations__.get(key)
            agent_data[key] = convert_value_to_type(
                value=getattr(agent_model, key), target_type=target_type
            )

    # Convert AgentConfigModel instances to Config
    configs = {}
    if hasattr(agent_model, "configs"):
        for config_model in agent_model.configs:
            key = getattr(config_model, "key")
            raw_value = getattr(config_model, "value")

            # Convert raw_value safely to a Python value first
            parsed_value = _safe_parse_value(raw_value)

            # Convert value to the type specified in ConfigsOutput if needed
            target_type = ConfigsOutput.__annotations__.get(key)

            if key == "sentiment_analyzer":
                # sentiment_analyzer may be JSON text, python-literal string, or already a dict
                value = parsed_value if parsed_value is not None else parsed_value
            elif target_type:
                # pass the parsed value into convert_value_to_type (it handles primitives/containers)
                value = convert_value_to_type(parsed_value, target_type)
            else:
                value = parsed_value

            configs[key] = value

    if hasattr(agent_model, "creator") and agent_model.creator:
        agent_data["creator"] = user_convert_model_to_response(agent_model.creator)

    agent_with_config = AgentWithConfigsOutput(
        agent=AgentOutput(**agent_data),
        configs=ConfigsOutput(**configs) if configs else None,
    )

    return agent_with_config


def convert_agents_to_agent_list(
    agents: List[AgentModel],
) -> List[AgentWithConfigsOutput]:
    return [convert_model_to_response(agent_model) for agent_model in agents]
