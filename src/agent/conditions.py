from agent.state import AgentState

def needs_more_info(state: AgentState) -> bool:
    # e.g., missing date range or entity ids
    return False

def failed_verification(state: AgentState) -> bool:
    # check verification_report flags
    return False
