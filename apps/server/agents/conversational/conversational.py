import asyncio

from agents.base_agent import BaseAgent
from agents.handle_agent_errors import handle_agent_error
from config import Config
from memory.zep.zep_memory import ZepMemory
from postgres import PostgresChatMessageHistory
from services.pubsub import ChatPubSubService
from services.run_log import RunLogsManager
from services.voice import speech_to_text, text_to_speech
from typings.agent import AgentWithConfigsOutput
from typings.config import AccountSettings, AccountVoiceSettings
from utils.model import get_llm
from utils.system_message import SystemMessageBuilder

# Import our new adapter
from agents.conversational.xagent_adapter import XAgentAdapter

class ConversationalAgent(BaseAgent):
    async def run(
        self,
        settings: AccountSettings,
        voice_settings: AccountVoiceSettings,
        chat_pubsub_service: ChatPubSubService,
        agent_with_configs: AgentWithConfigsOutput,
        tools, # This is now ignored by our implementation
        prompt: str,
        voice_url: str,
        history: PostgresChatMessageHistory,
        human_message_id: str,
        run_logs_manager: RunLogsManager,
        pre_retrieved_context: str,
    ):
        memory = ZepMemory(
            session_id=str(self.session_id),
            url=Config.ZEP_API_URL,
            api_key=Config.ZEP_API_KEY,
            memory_key="chat_history",
            return_messages=True,
        )

        memory.human_name = self.sender_name
        memory.ai_name = agent_with_configs.agent.name

        system_message = SystemMessageBuilder(
            agent_with_configs, pre_retrieved_context
        ).build()

        res: str

        try:
            if voice_url:
                configs = agent_with_configs.configs
                prompt = speech_to_text(voice_url, configs, voice_settings)

            # --- START: Langchain Agent Replacement ---

            # 1. Format conversation history and prompt into a single task for XAgent.
            chat_history = memory.load_memory_variables({}).get("chat_history", [])
            full_task_description = (
                "You are an advanced AI assistant. Please perform the following task based on the "
                "conversation history and the latest user request.\n\n"
                "--- Conversation History ---\n"
            )
            for msg in chat_history:
                full_task_description += f"[{msg.type.upper()}]: {msg.content}\n"
            
            full_task_description += (
                f"\n--- Latest User Request ---\n{prompt}\n\n"
                f"--- System Instructions ---\n{system_message}\n"
            )

            # 2. Instantiate and run the XAgentAdapter.
            # IMPORTANT: We will place XAgent's config file in the L3AGI server's root.
            xagent_config_path = "xagent_config.yml" 
            adapter = XAgentAdapter(config_file=xagent_config_path)
            
            # The adapter runs the task and returns the final result as a single string.
            # We yield it to fit into the async generator structure of the `run` method.
            res = await adapter.run(task=full_task_description)
            yield res

            # --- END: Langchain Agent Replacement ---

        except Exception as err:
            res = handle_agent_error(err)
            yield res

        # The rest of the function remains the same for handling voice output and PubSub
        try:
            configs = agent_with_configs.configs
            voice_url = None
            if "Voice" in configs.response_mode:
                voice_url = text_to_speech(res, configs, voice_settings)
        except Exception as err:
            res = f"{res}\n\n{handle_agent_error(err)}"
            yield res

        ai_message = history.create_ai_message(
            res,
            human_message_id,
            agent_with_configs.agent.id,
            voice_url,
        )

        chat_pubsub_service.send_chat_message(chat_message=ai_message)