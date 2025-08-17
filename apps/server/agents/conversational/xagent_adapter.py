import os
import asyncio

class XAgentAdapter:
    """
    Adapter to bridge the conversational L3AGI framework with the 
    task-driven XAgent framework.
    """
    def __init__(self, config_file: str):
        """
        Initializes the adapter and ensures XAgent's configuration is loaded
        before any other XAgent modules are imported.
        """
        # --- THIS IS THE CRITICAL CHANGE ---
        # We import and load the CONFIG object here, before any other
        # part of the application can import an XAgent module that needs it.
        from XAgent.config import CONFIG
        
        os.environ['CONFIG_FILE'] = config_file
        CONFIG.reload(config_file)
        # ------------------------------------

    async def run(self, task: str) -> str:
        """
        Runs a task using the XAgent framework. This method is asynchronous
        but runs the synchronous XAgent core in a separate thread to avoid blocking.

        Args:
            task (str): The comprehensive task description for XAgent.

        Returns:
            str: The final result from the XAgent execution.
        """
        # These imports are now safe because the CONFIG has been loaded.
        from XAgent.config import ARGS
        from XAgent.running_recorder import recorder
        from command import CommandLine, CommandLineParam
        
        ARGS['task'] = task
        
        param = CommandLineParam(
            task=ARGS.get('task'),
            role="Assistant",
            mode="auto",  # Ensure XAgent runs non-interactively
        )
        
        cmd = CommandLine(param)
        
        # Run the synchronous XAgent main logic in a thread pool executor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, cmd.start)
        
        # After execution, retrieve the result from XAgent's workspace.
        workspace_dir = recorder.record_root_dir
        
        final_output_content = f"Task completed successfully. No specific output file was found. Please check the XAgent workspace for all outputs at: {workspace_dir}"

        if os.path.exists(workspace_dir):
            files = [f for f in os.listdir(workspace_dir) if os.path.isfile(os.path.join(workspace_dir, f))]
            if files:
                report_files = [f for f in files if 'report' in f.lower() and f.endswith('.md')]
                if report_files:
                    latest_file_path = os.path.join(workspace_dir, report_files[0])
                else:
                    latest_file_path = max([os.path.join(workspace_dir, f) for f in files], key=os.path.getmtime, default=None)

                if latest_file_path:
                    with open(latest_file_path, "r", encoding="utf-8") as f:
                        final_output_content = f"Task completed. The primary output file is '{os.path.basename(latest_file_path)}'.\n\n--- FILE CONTENT ---\n{f.read()}"
        
        return final_output_content