# Job-Search Intelligence Questions

Each question is a ticket topic. Acceptance criterion for each ticket: the app answers the question on screen or in chat, and the answer reconciles with the underlying data.

---

## Tier 1 — Foundational Counts

Capability: pure `COUNT` once emails are classified.

Build phase: Dashboard, Phase 3.

- **Q-01:** How many jobs have I applied to, lifetime?
- **Q-02:** How many applications in a given window (this week / month / year)?
- **Q-03:** How many distinct companies have I applied to?
- **Q-04:** How many applications got at least one human response vs. total silence?
- **Q-05:** How many rejections have I received?
- **Q-06:** How many applications got no response at all (ghosted)?
- **Q-07:** How many interview invitations have I received?
- **Q-08:** How many offers have I received?
- **Q-09:** What's the current status of every application (applied / in-review / interview / rejected / offer / ghosted)?
- **Q-10:** Which applications are still "live" (awaiting a reply right now)?

## Tier 2 — Rates, Funnels & Time

Capability: ratios and date math on the same table.

Build phase: Dashboard, Phase 3.

- **Q-11:** What's my overall response rate?
- **Q-12:** What's my rejection rate?
- **Q-13:** What's my ghost rate (% that go silent)?
- **Q-14:** What's my application → interview conversion rate?
- **Q-15:** What's my interview → offer conversion rate?
- **Q-16:** What does my full funnel look like (applied → screen → interview → final → offer)?
- **Q-17:** What's the average time from applying to a first response?
- **Q-18:** What's the average time-to-rejection?
- **Q-19:** After how many days of silence is an application effectively dead? (my personal "ghost threshold")
- **Q-20:** How has my application volume trended over time?
- **Q-21:** Is my response rate improving over time — am I getting better?

## Tier 3 — Segmentation & Breakdowns

Capability: `GROUP BY` role / source / salary / tech / sponsorship.

Build phase: Dashboard, Phase 3.

- **Q-22:** Which job titles do I apply to most — and how does each convert?
- **Q-23:** Which roles get me the most interviews (best-converting titles)?
- **Q-24:** Which company types (startup vs. enterprise, by industry) respond best?
- **Q-25:** How do outcomes differ by application source (LinkedIn vs. company site vs. Indeed vs. referral)?
- **Q-26:** What salary bands am I targeting, and how do they convert?
- **Q-27:** How do remote vs. hybrid vs. onsite roles convert for me?
- **Q-28:** How many jobs I applied to offered visa sponsorship vs. didn't?
- **Q-29:** What's my response/interview rate for sponsorship vs. non-sponsorship roles?
- **Q-30:** Which tech stacks/skills show up in the jobs I apply to, and which ones convert best?
- **Q-31:** Which seniority levels (junior / mid / senior / lead) convert best for me?

## Tier 4 — Diagnostic & Comparative

Capability: correlations; what winners vs. losers share; light stats.

Build phase: Diagnostics, Phase 3.5–4.

- **Q-32:** What do my successful applications (interview/offer) have in common?
- **Q-33:** What do my rejected/ghosted applications have in common?
- **Q-34:** Which single factor correlates most with getting a response (role, source, salary, sponsorship, keywords)?
- **Q-35:** Am I pouring effort into a role/company-type that never converts?
- **Q-36:** Which application source gives the best ROI (interviews per application)?
- **Q-37:** Is my sponsorship requirement measurably hurting my response rate — and by how much?
- **Q-38:** Which of the skills I list actually "sell" (correlate with interviews) vs. which are dead weight?
- **Q-39:** Are there adjacent roles I don't apply to but should, given where I convert best?

## Tier 5 — Narrative "Why"

Capability: LLM synthesis over rejection/feedback text, cached.

Build phase: Insights page, Phase 4.

- **Q-40:** Why am I getting rejected — what are the recurring themes across rejection emails?
- **Q-41:** What does the recruiter/interviewer feedback consistently say I should improve?
- **Q-42:** Which technologies/skills keep appearing in roles I get rejected from (my real gaps)?
- **Q-43:** What are my strongest and weakest signals across the whole history?
- **Q-44:** Which roles genuinely suit me best, based on the pattern of my wins?
- **Q-45:** What are the 3 concrete things I should do next week to improve outcomes?
  Answer contract: the `weekly_actions` insight returns exactly three numbered, cited next-week actions.
- **Q-46:** What's the "story" my last 6–12 months of job searching tells?

## Tier 6 — Conversational Recall

Capability: hybrid RAG using semantic retrieval plus structured-query tools.

Build phase: Chat agent, Phase 5.

- **Q-47:** "What exactly did the recruiter at [Company] say in their last email?"
- **Q-48:** "Show me every rejection that mentioned experience / every company that mentioned sponsorship."
- **Q-49:** "Who am I waiting on, and who's overdue for a follow-up?" (feeds the draft phase later)
- **Q-50:** Free-form: ask anything about my job search in natural language, from my phone.

## Tier 7 — Predictive / Prescriptive / External

Capability: external data or job-board/recruiter APIs.

Build phase: Future, Phase 6+.

- **Q-51:** What's the probability this application converts, given my history?
- **Q-52:** How does my response rate compare to benchmarks for my role/market?
- **Q-53:** Which currently-open roles should I prioritize applying to next?
- **Q-54:** Is this company/recruiter still actively hiring / have they gone quiet on everyone?
