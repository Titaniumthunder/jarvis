# agents/diagram_agent.py
# Generates Mermaid.js diagrams from a natural language description.
# Supports: flowcharts, logic gates, sequence diagrams, class diagrams, state machines.

from tools import groq_tool

DIAGRAM_SYSTEM = """You are a Mermaid.js diagram generator.
The user will describe a diagram and you must return ONLY valid Mermaid.js syntax.
No explanation, no markdown fences, no comments — just the raw Mermaid syntax.

Supported diagram types:
- flowchart TD / flowchart LR  (flowcharts, decision trees, logic gates)
- sequenceDiagram              (interaction / timing diagrams)
- classDiagram                 (UML class diagrams)
- stateDiagram-v2              (state machines)
- erDiagram                    (entity-relationship)

For digital logic gates use flowchart shapes:
  Rectangular [Label]  = AND gate input/output
  Diamond {Label}      = decision / XOR
  Rounded (Label)      = signal / wire node
  Circle ((Label))     = NOT / bubble

Example — half-adder logic circuit:
flowchart LR
    A([Input A]) --> XOR1{XOR}
    B([Input B]) --> XOR1
    A --> AND1[AND]
    B --> AND1
    XOR1 --> Sum([Sum])
    AND1 --> Cout([Carry Out])

Example — simple flowchart:
flowchart TD
    A[Start] --> B{Is condition true?}
    B -->|Yes| C[Do this]
    B -->|No| D[Do that]
    C --> E[End]
    D --> E

Example — sequence diagram:
sequenceDiagram
    User->>Jarvis: Send command
    Jarvis->>Brain: Route action
    Brain-->>Jarvis: action + params
    Jarvis-->>User: Reply

Output ONLY the raw Mermaid syntax. Nothing else."""


def run(params: dict) -> str:
    """
    Generate a Mermaid diagram from a description.
    Returns "DIAGRAM:<mermaid_syntax>" on success, or "DIAGRAM_ERROR:<msg>" on failure.
    """
    description = params.get("description", "").strip()
    if not description:
        return "DIAGRAM_ERROR: No description provided"

    prompt = f"Generate a Mermaid.js diagram for: {description}"

    try:
        raw = groq_tool.ask(prompt, system=DIAGRAM_SYSTEM, temperature=0.2, max_tokens=600)
        code = _strip_fences(raw)
        if not code:
            return "DIAGRAM_ERROR: Got empty response"
        print(f"[diagram_agent] Generated {len(code)} chars of Mermaid")
        return f"DIAGRAM:{code}"
    except Exception as e:
        print(f"[diagram_agent] Error: {e}")
        return f"DIAGRAM_ERROR: {e}"


def _strip_fences(text: str) -> str:
    """Remove optional ```mermaid ... ``` fences that the LLM might include."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()
    return text
