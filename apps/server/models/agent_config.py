# ...existing code...
import uuid
import json
import ast
import logging
from typing import Any, List, Optional

from sqlalchemy import UUID, Column, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from models.base_model import BaseModel
from typings.agent import ConfigInput

logger = logging.getLogger(__name__)


class AgentConfigModel(BaseModel):
    """
    Agent related configurations like goals, instructions, constraints and tools are stored here
    """

    __tablename__ = "agent_config"

    id = Column(UUID, primary_key=True, index=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agent.id", ondelete="CASCADE"), index=True
    )
    key = Column(String, index=True)
    value = Column(Text)

    agent = relationship("AgentModel", back_populates="configs", cascade="all, delete")

    created_by = Column(
        UUID,
        ForeignKey("user.id", name="fk_created_by", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    modified_by = Column(
        UUID,
        ForeignKey("user.id", name="fk_modified_by", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    creator = relationship("UserModel", foreign_keys=[created_by], lazy="select")

    __table_args__ = (Index("ix_agent_config_model_agent_id_key", "agent_id", "key"),)

    def __repr__(self):
        return f"AgentConfig(id={self.id}, key={self.key}, value={self.value})"

    @staticmethod
    def _to_json_text(v: Any) -> Optional[str]:
        """
        Normalize a Python value or string into valid JSON text or None.
        - None -> None (store SQL NULL)
        - dict/list/bool/int/float -> json text
        - str -> if valid JSON text keep; else try ast.literal_eval then json.dumps; fallback json.dumps(str)
        - other -> json.dumps(str(v))
        """
        if v is None:
            return None
        if isinstance(v, (dict, list, bool, int, float)):
            try:
                return json.dumps(v, ensure_ascii=False)
            except Exception:
                return json.dumps(str(v), ensure_ascii=False)
        if isinstance(v, str):
            if v == "":
                # store empty string as JSON string ""
                return json.dumps(v, ensure_ascii=False)
            try:
                # already valid JSON text -> keep as-is
                json.loads(v)
                return v
            except Exception:
                # try python literal like "['a']" or "{'k': 'v'}"
                try:
                    parsed = ast.literal_eval(v)
                    return json.dumps(parsed, ensure_ascii=False)
                except Exception:
                    return json.dumps(v, ensure_ascii=False)
        try:
            return json.dumps(str(v), ensure_ascii=False)
        except Exception:
            return None

    @classmethod
    def create_or_update(cls, db, agent, update_configs, user, account) -> List["AgentConfigModel"]:
        """
        Create or update agent configurations in the database.
        Normalizes values into valid JSON text before persisting.
        """
        db_configs = (
            db.session.query(AgentConfigModel)
            .filter(AgentConfigModel.agent_id == agent.id)
            .all()
        )
        changes: List[AgentConfigModel] = []

        for key in ConfigInput.__annotations__.keys():
            raw_val = getattr(update_configs, key, None)
            normalized = cls._to_json_text(raw_val)
            logger.debug("agent_config prepare key=%s raw=%r normalized=%r", key, raw_val, normalized)

            # search db_configs
            matching_configs = [c for c in db_configs if getattr(c, "key", None) == key]
            if matching_configs:
                db_config = matching_configs[0]
                db_config.value = normalized
                db_config.modified_by = user.id
                changes.append(db_config)
            else:
                new_config = AgentConfigModel(
                    agent_id=agent.id, key=key, value=normalized
                )
                new_config.created_by = user.id
                changes.append(new_config)

        if changes:
            db.session.add_all(changes)
            db.session.commit()

        return changes

    @classmethod
    def create_configs_from_template(
        cls, db, configs, user, account, agent_id, check_is_template
    ) -> List["AgentConfigModel"]:
        """
        Create agent configurations from a template list.
        Normalizes template values into valid JSON text and resolves nested agent refs.
        """
        from models.agent import AgentModel  # local import to avoid circular deps

        def _parse_and_normalize_value(val: Any) -> Optional[str]:
            if val is None:
                return None
            if isinstance(val, (dict, list, bool, int, float)):
                try:
                    return json.dumps(val, ensure_ascii=False)
                except Exception:
                    return json.dumps(str(val), ensure_ascii=False)
            if isinstance(val, str):
                if val == "":
                    return json.dumps(val, ensure_ascii=False)
                try:
                    json.loads(val)
                    return val
                except Exception:
                    try:
                        parsed = ast.literal_eval(val)
                        return json.dumps(parsed, ensure_ascii=False)
                    except Exception:
                        return json.dumps(val, ensure_ascii=False)
            return json.dumps(str(val), ensure_ascii=False)

        changes: List[AgentConfigModel] = []
        for template_config in configs:
            raw_value = template_config.value
            normalized_value: Optional[str] = None

            if template_config.key == "sentiment_analyzer":
                # support JSON text or python-literal
                try:
                    try:
                        obj = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
                    except Exception:
                        obj = ast.literal_eval(raw_value) if isinstance(raw_value, str) else raw_value
                    runner = obj if isinstance(obj, dict) else {}
                except Exception:
                    runner = {}

                runner_id = runner.get("runner", None)
                if runner_id:
                    runner_model = AgentModel.create_agent_from_template(
                        db, runner_id, user, account, check_is_template
                    )
                    runner["runner"] = str(runner_model.id)

                normalized_value = json.dumps(runner, ensure_ascii=False)

            elif template_config.key == "runners":
                try:
                    try:
                        obj = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
                    except Exception:
                        obj = ast.literal_eval(raw_value) if isinstance(raw_value, str) else raw_value
                    runners = obj if isinstance(obj, list) else []
                except Exception:
                    runners = []

                for runner in runners:
                    runner_id = runner.get("runner", None)
                    if runner_id:
                        runner_model = AgentModel.create_agent_from_template(
                            db, runner_id, user, account, check_is_template
                        )
                        runner["runner"] = str(runner_model.id)

                normalized_value = json.dumps(runners, ensure_ascii=False)

            else:
                normalized_value = _parse_and_normalize_value(raw_value)

            logger.debug("template_config key=%s raw=%r normalized=%r", template_config.key, raw_value, normalized_value)

            new_config = AgentConfigModel(
                key=template_config.key,
                value=normalized_value,
                agent_id=agent_id,
                created_by=user.id,
            )
            changes.append(new_config)

        if changes:
            db.session.add_all(changes)
            db.session.commit()

        return changes
