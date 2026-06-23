---
name: council_review
description: Multi-persona adversarial review of a drafted article. Four reviewers: RF engineer (technical accuracy), security/red-team (misuse risk), skeptical editor (embellishment check), target reader (clarity). Produces annotated revision. Mandatory before any article is presented to the operator.
user-invocable: false
---

## How to call

```
python3 skills-scripts/council_review.py --draft-path /data/sdr/articles/draft-2026-06-23.md
```

## Output

Saves a `*-reviewed.md` file in the same directory with inline annotations and a final revised version. Returns JSON with a summary of findings per persona and whether the draft passed.

## Personas

1. **RF engineer** — checks technical claims against actual observations in the catalog. Flags any misstatement about frequencies, modulations, or measurements.
2. **Security / red-team** — checks whether the article contains operational detail that could aid misuse. Flags anything that should be redacted or reframed.
3. **Skeptical editor** — checks for embellishment, exaggeration, or unsubstantiated claims. "Did you actually observe this, or are you speculating?"
4. **Target reader (Hebrew-speaker, not RF expert)** — checks clarity, Hebrew grammar, RTL formatting, and whether technical terms are explained.
