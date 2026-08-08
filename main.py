"""TradeOracle Apex runtime entry point."""
from core.orchestrator import ApexOrchestrator

def main():
    result = ApexOrchestrator().run()
    print(result)
    return result

if __name__ == "__main__":
    main()
