# Building with the Claude API — track project

A supply-chain demand-forecasting and intelligence assistant for the AWS EC2 Mac
instance family, in one file: [`ec2_mac_forecaster.py`](ec2_mac_forecaster.py).

I built this for the Anthropic Academy "Building with the Claude API" track to make
every core concept concrete in working code rather than just notes.

## What it demonstrates

| Concept | Where, in the file |
| --- | --- |
| Messages API | the `client.messages.stream(...)` call in `converse()` |
| System prompt | the `SYSTEM` list (role block + handbook block) |
| Multi-turn history | the `messages` list grown by hand each turn (the API is stateless) |
| Streaming | the `for event in stream` loop printing thinking + text live |
| Tool use | `get_demand_forecast` / `get_capacity` + the run-and-feed-back loop |
| Prompt caching | `cache_control` on the static capacity handbook |
| Extended thinking | `thinking={"type": "adaptive", "display": "summarized"}` |

## Run it

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...     # read from env, never hardcoded
python3 ec2_mac_forecaster.py
```

It runs a scripted three-turn conversation: forecast + capacity for a pool in
us-east-1, the same for the thinner eu-west-1 pool, then a recommendation ahead of
an iOS GA. Watch the `[usage]` line each turn — on later turns `cache_read` should
be non-zero, showing the handbook being reused from cache instead of reprocessed.

## The lesson behind the design

The model has no memory across calls, can't fetch live data on its own, and is
expensive to re-feed. Every feature here answers one of those limits: history we
resend ourselves, tools for live numbers, caching so the static handbook isn't
re-billed each turn. That mapping — features as answers to model limits — is the
whole mental model of the course.

## Notes

- Built to current best practices: `claude-opus-4-8`, adaptive thinking, env-var
  key. Swap `MODEL` to Sonnet or Haiku for cheaper runs while learning.
- The tool data is mocked but deterministic; in production these would hit a real
  forecasting service and capacity database.
- Caching only engages above the model's minimum cacheable prefix (~4096 tokens
  for Opus). If `cache_write` shows 0, the handbook is below that threshold — a
  real lesson in itself.
