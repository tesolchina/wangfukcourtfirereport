# Pilot: coding one hearing day (27 April 2026, Day 20)

**Purpose** — test the instrument before scaling to all 31 transcripts. Day 20 was chosen
because it is the hardest case: Buildings Department and ICU witnesses, and the day with the
highest policy vocabulary in the earlier keyword scan (130 policy terms).

## 1. Parse

| Item | Value |
|---|---|
| Examination blocks | 7 |
| Question marks | 343 |
| Usable question turns (boilerplate removed) | 285 |
| Witnesses | 4 |

| Witness | Capacity | Questions | Share |
|---|---|---|---|
| Ms Cheung Yuk Ching, Karen | Assistant Director, Buildings Department (mandatory building inspection) | 199 | 58% |
| Ms Or Wai Yin | Liaison Officer, Home Affairs Dept / Tai Po District Office; seconded to ICU 2023–25 | 98 | 29% |
| Mr Tse Kam Ming | Retired Senior Building Surveyor, BD; formerly seconded to ICU | 27 | 8% |
| Ms Chan Hau Man | District Officer, Tai Po | 19 | 6% |

One witness absorbed 58% of the day's questions.

## 2. Hand-coded sample (40 questions, every 7th)

Coding rule: *could an officer who only applies the rule answer this?* Yes → implementation.
Requires knowing why a rule, standard, penalty or delegation was set as it was → formulation.

| Code | n |
|---|---|
| Implementation | 35 |
| Procedural / document reference | 5 |
| **Formulation** | **0** |

## 3. Keyword rule is unusable on its own

A regex for `why|policy|standard|guideline|requirement|decide|adequate|review|penalty|bureau`
returned **27 hits**. Hand-coding them:

- **24 were implementation** — "why did you not notify in advance", "why no audit has been done",
  "why this escalation in your tone", "the ISO standard is referred to elsewhere".
- **3 were formulation-adjacent** — why natural lighting is required; why a consistency clause
  exists; the delegation of BD powers to the ICU.

Precision ≈ 11%. Keyword counting cannot carry this analysis; the coding has to be judgment-based.

## 4. Deflections: none upward

Five witness answers contained policy or incapacity language. None was a referral to the bureau:

- "that case falls outside our purview so I'm not in a position to give you an answer" (jurisdiction)
- "I cannot answer the question" (knowledge)
- "I can't answer you on this" (knowledge)

**No witness said the question belonged to the policy level.** That is the finding that matters:
the committee did not put the questions that would have produced such answers.

## 5. The most policy-adjacent exchange on the day

The Chairman, on the BD's delegation to the ICU:

> "The BD delegated its powers to the ICU. You cannot answer whether there was communication
> between the ICU and the FSD, but the BD should be part of the loop. So we should review this
> communication mechanism. Is there anything amiss?"

The witness answered with what the department is doing — a working group with FSD, Labour and
the ICU. The delegation itself — who designed it, why the ICU was given those powers, whether
the arrangement was sound — was not put. Even the day's most policy-adjacent question stayed
at the level of coordination.

## 6. What this means for scaling

1. **The instrument works.** Blocks parse cleanly, witnesses and capacities are recoverable,
   question counts are exact.
2. **Keyword coding must be dropped.** Precision of 11% would manufacture findings.
3. **Code at block level with a model**, 186 blocks across 31 transcripts (~5.1 MB), then
   hand-code 20 blocks as a reliability check and report agreement.
4. **Add the deflection code** — it is the sharpest evidence available, and on this day it
   returned zero, which is itself the point.

## Caveats

Single coder (the agent), no second coder yet; one day only; English transcripts only
(the Chinese originals are authoritative where they differ); "formulation" is a judgment
call at the margins, which is why the reliability check matters before any number is published.
