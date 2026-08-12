# Portability

The core package accepts versioned JSON and has no Agent SDK dependency. Install SDK
adapters only in an integration environment:

```bash
python -m venv .venv-sdk
.venv-sdk/bin/python -m pip install -e ".[sdk,test]"
```

`react-agent[langgraph]` retains a historical LangGraph 0.2 experiment, while this package
tests LangGraph 1.x. They are deliberately isolated instead of forcing incompatible SDKs
into one interpreter. Export `evaluation-episode/v1` from the Agent environment and import
the JSON here. The evaluator and `trace-debugger` do not import the producing SDK.

The SDK tests use a real LangGraph graph and a real OpenAI Agents Runner with a local
deterministic model. Remote model quality and availability remain separate concerns.
