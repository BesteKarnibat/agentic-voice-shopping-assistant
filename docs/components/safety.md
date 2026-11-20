# Safety considerations

**Owner:** Beste · **Branch:** `feature/eval` · **Status:** todo
**Code / prompts:** TODO · [../../prompts/guardrails.md](../../prompts/guardrails.md)

## 1. Threat model
<!-- What can go wrong: unsafe chemical advice (mixing cleaners), prompt injection via web results or reviews, hallucinated claims, off-topic requests, leaking secrets. -->
| Risk | Example | Mitigation | Where enforced |
|------|---------|------------|----------------|
| Unsafe chemical advice | "Can I mix bleach and ammonia?" | TODO | `router` (input), `critic` (output) |
| Prompt injection in web content | TODO | TODO | |
| Ungrounded claims | TODO | Citation required, Critic grounding check | `critic` |
| Untrusted web sources | TODO | Domain allowlist | `web.search` |
| Secrets in repo | TODO | `.env` gitignored, `.env.example` empty | repo |

## 2. Input guardrails
TODO

## 3. Output guardrails
<!-- Critic checks, refusal/safe-completion behavior, wording for hazardous combinations. -->
TODO

## 4. Grounding and citation policy
<!-- No citation, no claim. How it is checked. -->
TODO

## 5. Adversarial cases tested
<!-- Link to the scenarios in evaluation.md and summarize pass/fail. -->
TODO

## 6. Limitations
TODO
