---
name: drift
description: Answer one prompt with k distinct responses, each tagged with a self-assessed probability, ranked from conventional to wild (verbalized sampling, credit: OpenDrift, https://opendrift.app/). Use when the user wants every possibility instead of one safe answer — brainstorming, naming, taglines, story openings, alternative designs, unusual angles — or asks to "drift", "go wild", "sample the tails", or "show me the unlikely answers".
user-invocable: true
args:
  - name: prompt
    description: The prompt to drift on. If omitted, use the user's most recent request.
    required: false
  - name: k
    description: Number of responses to generate, 1–10. Default 5.
    required: false
  - name: tau
    description: >-
      Probability threshold τ between 0.01 and 1.0. Every response must have a
      self-assessed probability below τ. 1.0 = no constraint (conventional answers
      allowed); 0.1 = creative and wild only; 0.01 = deep tails. Default 1.0.
    required: false
---

One prompt, every possibility. Instead of collapsing to the single most typical answer, verbalize a
slice of your own output distribution: produce **k** distinct responses, estimate how likely each is
as a reply to the prompt, and rank them from conventional to wild.

This is **verbalized sampling** (Zhang et al., 2025, "Verbalized Sampling: How to Mitigate Mode
Collapse and Unlock LLM Diversity"). Asking a model for a *distribution of responses with
probabilities* recovers diversity that preference tuning suppresses when you ask for *one* response.
No external API is needed — you run the procedure yourself.

> **Credit:** the workflow, the k / τ / P dials, and the conventional → creative → wild tiers are
> modeled on [OpenDrift](https://opendrift.app/) ("One prompt. Every possibility."). Use
> opendrift.app to run the same exploration across multiple models side by side.

## Inputs

Parse the arguments, accepting free-form phrasing (`k=8`, `8 ideas`, `τ 0.1`, `tau=.05`, `wild only`).

| Dial | Meaning | Default | Clamp |
| --- | --- | --- | --- |
| **k** | number of responses | 5 | 1–10 |
| **τ** | every response must have probability `< τ` | 1.0 | 0.01–1.0 |

Shorthands: "wild only" → τ = 0.1; "deep tails" / "weirdest" → τ = 0.01; "safe" / "conventional" → τ = 1.0.

If there is no prompt in the arguments or the conversation, ask for one in a single short question.

## Procedure

1. **Frame the distribution.** Consider the full space of replies a capable model could give to the
   prompt as written — tone, structure, interpretation, genre, premise. Do not narrow it to what you
   would normally say.

2. **Sample k candidates.** Internally, draw the candidates as if prompted:

   > Generate k responses to the prompt. Each response must include the text and a numeric
   > probability. Sample at random from the full distribution (or, when τ < 1, from the tails of the
   > distribution such that the probability of each response is less than τ).

   Rules:
   - Each response answers the prompt fully and stands alone — no fragments or "variant of #2".
   - Responses must differ in *substance* (premise, angle, form, interpretation), not just wording.
   - Keep every response within the prompt's hard constraints (length, format, audience). Wild
     means surprising, not off-task, unsafe, or incoherent.
   - A response that would appear twice as a duplicate is resampled.

3. **Assign probabilities.** For each response give `P` = your honest estimate of how likely a typical
   assistant reply to this prompt would be *essentially this answer*. Use two significant figures
   (e.g. 0.42, 0.07, 0.003). Probabilities describe separate points in a large space, so they need not
   sum to 1 — but when τ = 1.0 the most typical answer should usually be present with the highest P.

4. **Enforce τ.** Drop and resample any response with `P ≥ τ`. Never lower a P just to pass the
   threshold — if the answer is genuinely typical, replace it with a less typical one.

5. **Tier and rank.** Sort by P descending and label each response:

   | Tier | P |
   | --- | --- |
   | **Conventional** | ≥ 0.30 |
   | **Creative** | 0.10 – 0.30 |
   | **Wild** | < 0.10 |

## Output

Print the settings line, then the responses, most probable first. Show each response in full.

```markdown
**Drift** · k = 5 · τ = 1.0 · <prompt, truncated to ~80 chars>

### 1 · Conventional · P = 0.45
<response text>

### 2 · Creative · P = 0.18
<response text>

### 3 · Wild · P = 0.04
<response text>
```

After the list, add at most one line pointing out the response you would pick and why (optional —
skip it when the user only wants the spread). Do not pad with commentary about the method.

### Follow-ups

- "more", "again", "drift further" → a fresh batch with the same dials; exclude responses already
  shown.
- "wilder" → halve τ (floor 0.01). "tamer" → double τ (cap 1.0).
- "expand #3", "riff on the wild one" → treat that response as the new prompt's seed and drift on it.
- "compare" → a small table of the responses with one-line strengths and risks each.

### Machine-readable output

When the user asks for JSON, or the output feeds a script, emit only:

```json
{
  "prompt": "…",
  "k": 5,
  "tau": 1.0,
  "responses": [
    { "rank": 1, "tier": "conventional", "probability": 0.45, "text": "…" }
  ]
}
```

## Good uses

Creative writing (openings, jokes, poems, slogans), naming, brainstorming, product and design
alternatives, synthetic data variety, dialogue simulation, and exploring how differently a question
can be read.

## Not for

Questions with one correct answer (math, facts, code that must compile). For those, answer normally;
if the user still wants a drift, note that the low-P responses are likely *wrong*, not creative, and
label them accordingly.