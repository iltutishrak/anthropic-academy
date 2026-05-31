# Prompt Library

A reusable, growing set of prompt templates built on the Claude 101 five-block model:
**Role · Task · Context · Format · Source material.** Copy one, fill the brackets, paste.

> Tip from Claude 101: a few-shot example beats adjectives. Where a template says
> "[paste a real example]", paste an actual sample you like, not a placeholder.

---

## The master template

```
You are [ROLE].
[TASK: what you want, specifically.]
Context: [who it is for, what matters, any constraints].
Format: [length, structure, tone].
Here is the source material: [paste the actual content].
Here is an example of output I like: [paste a real example].
```

---

## Ready-to-use templates

### 1. Work email (from the Claude 101 exercise)
```
You are an expert AI product manager in supply chain.
Draft an email to my direct reports explaining the importance of agentic AI
in supply chain solutions.
Context: the team is technical but new to agentic patterns; I want them to act, not just read.
Format: about 100 words, simple, short, logical, concise. End with one concrete ask.
Here is an email style I like: [paste a real email you admire].
```

### 2. Summarize a document (grounded, reliable)
```
You are a precise analyst.
Summarize the document below for [audience].
Format: 5 bullet points, then one "so what" line on what I should do.
Only use what is in the document. If something is not stated, say so.
Document: [paste the full text].
```

### 3. Rewrite for tone
```
You are an editor.
Rewrite the text below to be [tone: e.g. warmer / more concise / less salesy].
Keep the meaning and any facts unchanged. Do not add new claims.
Text: [paste].
```

### 4. Decision pressure-test (anti-sycophancy)
```
You are a skeptical advisor.
Here is a decision I am leaning toward: [describe it].
Argue the strongest case against it first. Surface the assumptions I have not tested.
Then give your honest recommendation.
```

### 5. Explain to learn
```
You are a patient tutor. Assume I know nothing about [topic].
Explain it from first principles, in short modules, with one concrete example each.
After each module, check my understanding with one question before continuing.
```

---

## How to use this
- When output disappoints, scan the five blocks and add whatever is missing.
- For anything live, specific, or obscure, put the real info in the prompt (upload, paste, or a tool). Do not rely on the model's memory.
- Keep adding templates here as I find prompts that work.
