"""TradeOracle Apex launcher."""
from core.orchestrator import ApexOrchestrator

if __name__ == "__main__":
    print(ApexOrchestrator().run())
