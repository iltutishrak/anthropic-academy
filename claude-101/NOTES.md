# Claude 101 — Notes

My distilled notes from working through Claude 101. Written to be re-readable, not exhaustive.

## 1. What Claude is
Claude is a large language model: an AI assistant you talk to in plain language. It does not retrieve documents like a search engine. It **generates** the most useful continuation of the conversation, token by token, from patterns it learned in training. Mental model: an extremely well-read colleague who reasons and drafts on the spot, working from understanding rather than looking things up.

**The consequence:** because it generates rather than looks up, it can be **confidently wrong** (hallucination). The skill is knowing *when* output needs verification.

## 2. The three doors (same model, different access)
- **Door 1 - the apps (claude.ai, desktop, mobile):** Claude wrapped in a product for an end user. The consumer surface.
- **Door 2 - the API (platform.claude.com):** Claude as raw capability for developers to build on. Every "AI feature" inside someone else's product goes through here. This is the developer platform and the API Growth focus.
- **Door 3 - Claude Code:** Claude as an agent in the terminal with hands on your machine.

Sorting test: not "what topic is it" but "who built the product and how are they getting Claude." Anthropic's own product = Door 1 or 3. Someone else's product with Claude inside = Door 2 (the API).

## 3. Strengths and weaknesses
**Strong:** language transformation (summarize, rewrite, translate), drafting, reasoning over text you provide, explanation, code.

**Weak (the four to remember):**
1. Hallucination - invents plausible but false facts/citations.
2. Math and precise calculation - predicts the look of an answer.
3. Recency - knowledge cutoff; no native knowledge of recent events.
4. No memory across separate conversations.

**Master key:** Claude is strongest when the information it needs is **in the prompt**, weakest when relying on training memory. Good products and prompts are mostly about getting the right info in front of it.

## 4. Memory and context
- Within one continuous conversation, Claude remembers everything said (it is all in the **context window**, its working desk).
- A new, separate conversation is a clean slate.
- Very long conversations can overflow the context window (the "context reset" problem).
- "Memory" in products is not the model remembering. It is persistence layered on top: relevant context re-fed at the start (Projects, memory files, journals).

## 5. claude.ai features map to weaknesses
| Feature | Weakness it patches |
|---|---|
| File uploads | info not in the prompt |
| Web search | recency / knowledge cutoff |
| Projects | no memory across chats |
| Artifacts | output buried / not iterable |

PM insight: good AI products are systematically built to patch the model's weak spots.

## 6. Prompting
A strong prompt usually has five blocks: **Role, Task, Context, Format, Source material**. When output disappoints, one of these is usually missing.

Habits: show real examples (few-shot) beats describing; for hard tasks say "think step by step"; iterate instead of restarting. Mindset: treat Claude like a brilliant colleague on their first day - specificity is respect.
