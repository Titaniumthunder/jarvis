# orchestrator.py
# Receives a validated action dict from brain.py and routes it to the right agent.
#
# Think of this as a traffic controller: it reads the "action" field and
# calls the correct agent function, then returns the agent's response.

from agents import arm_agent, computer_agent, cad_agent, knowledge_agent, vision_agent, code_agent, blender_mcp_agent, blender_claude_agent, memory_agent, diagram_agent
from tools import time_tool

# Map each action name to the function that handles it.
# When you add a new action, register it here.
ACTION_ROUTER = {
    "get_time":       lambda params: time_tool.get_current_time(),
    "move_arm":       lambda params: arm_agent.run(params),
    "search_files":    lambda params: computer_agent.run({"task": "search_files", **params}),
    "web_search":      lambda params: computer_agent.run({"task": "web_search", **params}),
    "open_in_browser": lambda params: computer_agent.run({"task": "open_in_browser", **params}),
    "run_command":     lambda params: computer_agent.run({"task": "run_command", **params}),
    "generate_image":   lambda params: cad_agent.run({**params, "task": "generate_image"}),
    "generate_cad":     lambda params: cad_agent.run({**params, "task": "generate_cad"}),
    "generate_shape_e": lambda params: cad_agent.run({**params, "task": "generate_shape_e"}),
    "open_bambu":       lambda params: cad_agent.run({"task": "open_bambu", **params}),
    "answer_question": lambda params: knowledge_agent.run(params),
    "get_info":        lambda params: knowledge_agent.run(params),  # alias
    "watch_printer":  lambda params: vision_agent.run(params),
    "write_code":          lambda params: code_agent.run({**params, "task": "write_code"}),
    "edit_file":           lambda params: code_agent.run({**params, "task": "edit_file"}),
    "explain_code":        lambda params: code_agent.run({**params, "task": "explain_code"}),
    "generate_blender_mcp": lambda params: blender_mcp_agent.run(params),
    "refine_blender_mcp":   lambda params: blender_mcp_agent.refine(params),
    "generate_blender_cc":  lambda params: blender_claude_agent.run(params),   # Claude-powered
    "refine_blender_cc":    lambda params: blender_claude_agent.refine(params),
    "remember":             lambda params: memory_agent.run({**params, "task": "remember"}),
    "recall":               lambda params: memory_agent.run({**params, "task": "recall"}),
    "generate_diagram":     lambda params: diagram_agent.run(params),
    "clarify":        lambda params: params.get("question", "Could you clarify what you mean?"),
    "unknown":        lambda params: "I'm not sure how to do that yet.",
}


def dispatch(brain_response: dict) -> str:
    """
    Route a validated brain response to the correct agent.

    Args:
        brain_response: The dict returned by brain.ask() — already validated.

    Returns:
        A string result from the agent (to be spoken aloud or printed).
    """
    action = brain_response.get("action", "unknown")
    params = brain_response.get("params", {})
    reply  = brain_response.get("reply", "")

    handler = ACTION_ROUTER.get(action)
    if handler is None:
        return f"No handler registered for action '{action}'."

    # Run the agent and get its result
    agent_result = handler(params)

    # Factual actions: return ONLY the real result — never the LLM's guess.
    FACTUAL_ACTIONS = {"get_time", "search_files", "run_command", "web_search", "open_in_browser"}
    if action in FACTUAL_ACTIONS:
        return agent_result

    # Structured-result actions: return the raw agent result so the server can
    # parse special prefixes like "IMAGE:/path/..." or "CODE_FILE:/path/..." or
    # "DIAGRAM:..." without the reply text prepended.
    STRUCTURED_ACTIONS = {"generate_image", "write_code", "edit_file", "generate_diagram"}
    if action in STRUCTURED_ACTIONS:
        return agent_result

    # For everything else, combine the spoken reply with the agent result
    if agent_result and agent_result != reply:
        return f"{reply}\n{agent_result}"
    return reply
