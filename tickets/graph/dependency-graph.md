# Dependency graph

Generated: 2026-07-03T15:16:06Z

Tickets in the same stage have no dependencies on each other and can run in parallel.
A stage may start only when every earlier stage is done.

## Stage 1 (2 tickets)

- JT-002 (#2) Initialize monorepo structure [deps: JT-001]
- JT-003 (#3) Add root project metadata [deps: none]

## Stage 2 (31 tickets)

- JT-004 (#4) Scaffold backend Python project [deps: JT-002]
- JT-005 (#5) Configure backend linting and formatting [deps: JT-002]
- JT-006 (#6) Configure backend type checking [deps: JT-002]
- JT-007 (#7) Add backend test harness [deps: JT-002]
- JT-008 (#8) Create FastAPI app factory [deps: JT-002]
- JT-010 (#10) Add typed API error model [deps: JT-002]
- JT-011 (#11) Add Pydantic settings shell [deps: JT-002]
- JT-012 (#12) Add env example [deps: JT-002]
- JT-013 (#13) Add secret-store interface [deps: JT-002]
- JT-016 (#16) Add secret redaction utilities [deps: JT-002]
- JT-017 (#17) Add SQLite engine module [deps: JT-002]
- JT-023 (#23) Create base repository module [deps: JT-002]
- JT-026 (#26) Define EmailProvider interface [deps: JT-002]
- JT-027 (#27) Define LLMProvider interface [deps: JT-002]
- JT-028 (#28) Add provider registry [deps: JT-002]
- JT-029 (#29) Add setup status API shell [deps: JT-002]
- JT-032 (#32) Add local wipe-data command or endpoint [deps: JT-002]
- JT-033 (#33) Scaffold frontend Vite React TypeScript app [deps: JT-002]
- JT-034 (#34) Configure frontend lint and type checks [deps: JT-002]
- JT-035 (#35) Add frontend API client placeholder [deps: JT-002]
- JT-036 (#36) Add backend OpenAPI schema generator [deps: JT-002]
- JT-042 (#42) Add shared accessible UI primitives [deps: JT-002]
- JT-045 (#45) Add synthetic fixture format [deps: JT-002]
- JT-047 (#47) Add backend CI workflow [deps: JT-002]
- JT-048 (#48) Add frontend CI workflow [deps: JT-002]
- JT-049 (#49) Add pre-commit configuration [deps: JT-002]
- JT-050 (#50) Add local developer README [deps: JT-002]
- JT-051 (#51) Add Google OAuth setup guide [deps: JT-002]
- JT-052 (#52) Add LLM provider setup guide [deps: JT-002]
- JT-053 (#53) Add setup wizard copy [deps: JT-002]
- JT-054 (#54) Add minimal Playwright smoke harness [deps: JT-002]

## Stage 3 (31 tickets)

- JT-009 (#9) Add health endpoint [deps: JT-002, JT-008]
- JT-014 (#14) Implement keyring secret store [deps: JT-002, JT-013]
- JT-015 (#15) Implement Fernet secret fallback [deps: JT-002, JT-013]
- JT-018 (#18) Add sqlite-vec loading hook [deps: JT-002, JT-017]
- JT-019 (#19) Configure Alembic migrations [deps: JT-002, JT-017]
- JT-024 (#24) Add repository stubs [deps: JT-002, JT-023]
- JT-030 (#30) Add setup submit API shell [deps: JT-002, JT-029]
- JT-031 (#31) Add provider config API shell [deps: JT-002, JT-028]
- JT-037 (#37) Add TypeScript client generation workflow [deps: JT-002, JT-036]
- JT-038 (#38) Add setup page shell [deps: JT-002, JT-033, JT-042]
- JT-039 (#39) Add dashboard page shell [deps: JT-002, JT-033, JT-042]
- JT-040 (#40) Add insights page shell [deps: JT-002, JT-033, JT-042]
- JT-041 (#41) Add chat page shell [deps: JT-002, JT-033, JT-042]
- JT-043 (#43) Add Recharts foundation [deps: JT-002, JT-033]
- JT-044 (#44) Add frontend route query helper [deps: JT-002, JT-033]
- JT-046 (#46) Add synthetic fixture loader [deps: JT-002, JT-045]
- JT-055 (#55) Implement Gmail auth URL endpoint [deps: JT-013, JT-017, JT-026]
- JT-058 (#58) Add Gmail provider skeleton [deps: JT-013, JT-017, JT-026]
- JT-059 (#59) Implement Gmail message listing [deps: JT-013, JT-017, JT-026]
- JT-061 (#61) Implement broad candidate query strategy [deps: JT-013, JT-017, JT-026]
- JT-063 (#63) Implement HTML-to-text normalization [deps: JT-013, JT-017, JT-026]
- JT-065 (#65) Add raw email retention flags [deps: JT-013, JT-017, JT-026]
- JT-066 (#66) Implement full backfill state tracking [deps: JT-013, JT-017, JT-026]
- JT-068 (#68) Add backfill reconciliation metrics [deps: JT-013, JT-017, JT-026]
- JT-069 (#69) Store Gmail history ID [deps: JT-013, JT-017, JT-026]
- JT-071 (#71) Handle expired history IDs [deps: JT-013, JT-017, JT-026]
- JT-072 (#72) Add sync job status model [deps: JT-013, JT-017, JT-026]
- JT-073 (#73) Add sync service [deps: JT-013, JT-017, JT-026, JT-069]
- JT-075 (#75) Add APScheduler sync-on-open hook [deps: JT-013, JT-017, JT-026]
- JT-079 (#79) Add ingestion error handling [deps: JT-013, JT-017, JT-026]
- JT-080 (#80) Add ingestion smoke tests [deps: JT-013, JT-017, JT-026]

## Stage 4 (7 tickets)

- JT-020 (#20) Create initial core schema migration [deps: JT-002, JT-019]
- JT-056 (#56) Implement Gmail OAuth callback [deps: JT-013, JT-017, JT-026, JT-055]
- JT-060 (#60) Implement Gmail metadata normalization [deps: JT-013, JT-017, JT-026, JT-059]
- JT-062 (#62) Implement retained body fetching [deps: JT-013, JT-017, JT-026, JT-061]
- JT-067 (#67) Implement full backfill service [deps: JT-013, JT-017, JT-026, JT-066]
- JT-070 (#70) Implement incremental sync [deps: JT-013, JT-017, JT-026, JT-069]
- JT-074 (#74) Add sync API routes [deps: JT-013, JT-017, JT-026, JT-073]

## Stage 5 (8 tickets)

- JT-021 (#21) Add manual override schema migration [deps: JT-002, JT-020]
- JT-022 (#22) Add chat history schema migration [deps: JT-002, JT-020]
- JT-025 (#25) Add Pydantic domain DTOs [deps: JT-002, JT-020]
- JT-057 (#57) Implement Gmail token refresh [deps: JT-013, JT-017, JT-026, JT-056]
- JT-064 (#64) Implement raw email repository writes [deps: JT-013, JT-017, JT-026, JT-060, JT-062]
- JT-076 (#76) Add sync status frontend panel [deps: JT-013, JT-017, JT-026, JT-074]
- JT-077 (#77) Add sync-now UI action [deps: JT-013, JT-017, JT-026, JT-074]
- JT-078 (#78) Add Gmail auth frontend flow [deps: JT-013, JT-017, JT-026, JT-055, JT-056]

## Stage 6 (17 tickets)

- JT-081 (#81) Implement heuristic sender signals [deps: JT-027, JT-064, JT-073]
- JT-082 (#82) Implement heuristic keyword signals [deps: JT-027, JT-064, JT-073]
- JT-084 (#84) Persist filter decisions [deps: JT-027, JT-064, JT-073]
- JT-086 (#86) Implement Azure OpenAI provider [deps: JT-027, JT-064, JT-073]
- JT-087 (#87) Implement Ollama provider [deps: JT-027, JT-064, JT-073]
- JT-088 (#88) Add LLM provider health checks [deps: JT-027, JT-064, JT-073]
- JT-089 (#89) Add classification prompt contract [deps: JT-027, JT-064, JT-073]
- JT-090 (#90) Add classification DTOs [deps: JT-027, JT-064, JT-073]
- JT-093 (#93) Add extraction schema [deps: JT-027, JT-064, JT-073]
- JT-095 (#95) Handle malformed LLM output [deps: JT-027, JT-064, JT-073]
- JT-096 (#96) Track classification tokens and cost [deps: JT-027, JT-064, JT-073]
- JT-097 (#97) Add pre-run classification estimate [deps: JT-027, JT-064, JT-073]
- JT-098 (#98) Add classification mode config [deps: JT-027, JT-064, JT-073]
- JT-099 (#99) Add golden set fixture file [deps: JT-027, JT-064, JT-073]
- JT-102 (#102) Implement company normalization [deps: JT-027, JT-064, JT-073]
- JT-103 (#103) Implement role normalization [deps: JT-027, JT-064, JT-073]
- JT-109 (#109) Add reprocessing version controls [deps: JT-027, JT-064, JT-073]

## Stage 7 (5 tickets)

- JT-083 (#83) Implement candidate scoring [deps: JT-027, JT-064, JT-073, JT-081, JT-082]
- JT-091 (#91) Implement LLM classification service [deps: JT-027, JT-064, JT-073, JT-086, JT-087, JT-089, JT-090]
- JT-094 (#94) Implement structured extraction service [deps: JT-027, JT-064, JT-073, JT-093]
- JT-100 (#100) Add golden set eval runner [deps: JT-027, JT-064, JT-073, JT-099]
- JT-104 (#104) Implement application grouping key [deps: JT-027, JT-064, JT-073, JT-102, JT-103]

## Stage 8 (4 tickets)

- JT-085 (#85) Validate filter against golden set [deps: JT-027, JT-064, JT-073, JT-083, JT-099]
- JT-092 (#92) Persist email classifications [deps: JT-027, JT-064, JT-073, JT-091]
- JT-101 (#101) Enforce golden set gate [deps: JT-027, JT-064, JT-073, JT-100]
- JT-105 (#105) Implement application upsert [deps: JT-027, JT-064, JT-073, JT-104]

## Stage 9 (4 tickets)

- JT-106 (#106) Implement event timeline upsert [deps: JT-027, JT-064, JT-073, JT-105]
- JT-111 (#111) Add manual merge API [deps: JT-021, JT-027, JT-064, JT-073, JT-105]
- JT-112 (#112) Add manual split API [deps: JT-021, JT-027, JT-064, JT-073, JT-105]
- JT-116 (#116) Add application detail API [deps: JT-027, JT-064, JT-073, JT-105]

## Stage 10 (4 tickets)

- JT-107 (#107) Implement status derivation [deps: JT-027, JT-064, JT-073, JT-106]
- JT-113 (#113) Add manual status and event edit API [deps: JT-021, JT-027, JT-064, JT-073, JT-106]
- JT-117 (#117) Add application events API [deps: JT-027, JT-064, JT-073, JT-106]
- JT-118 (#118) Add applications list API [deps: JT-027, JT-064, JT-073, JT-116]

## Stage 11 (5 tickets)

- JT-108 (#108) Implement ghost inference [deps: JT-027, JT-064, JT-073, JT-107]
- JT-114 (#114) Implement correction locks [deps: JT-027, JT-064, JT-073, JT-111, JT-112, JT-113]
- JT-119 (#119) Add application correction UI [deps: JT-027, JT-064, JT-073, JT-111, JT-112, JT-113]
- JT-181 (#181) Add insights repository [deps: JT-020, JT-027, JT-118]
- JT-182 (#182) Add insight input builder [deps: JT-027, JT-118]

## Stage 12 (4 tickets)

- JT-110 (#110) Add aggregation idempotency tests [deps: JT-027, JT-064, JT-073, JT-105, JT-106, JT-108]
- JT-115 (#115) Implement correction conflict detection [deps: JT-027, JT-064, JT-073, JT-114]
- JT-183 (#183) Add insight staleness detection [deps: JT-027, JT-118, JT-181, JT-182]
- JT-184 (#184) Implement insight generation service [deps: JT-027, JT-086, JT-087, JT-118, JT-182]

## Stage 13 (10 tickets)

- JT-120 (#120) Add Phase 2 pipeline smoke test [deps: JT-027, JT-064, JT-073, JT-085, JT-091, JT-094, JT-110]
- JT-185 (#185) Add insight grounding validator [deps: JT-027, JT-118, JT-184]
- JT-186 (#186) Add insights API routes [deps: JT-027, JT-118, JT-181, JT-184]
- JT-189 (#189) Answer Q-40 recurring rejection themes [deps: JT-118, JT-184]
- JT-190 (#190) Answer Q-41 recurring recruiter feedback [deps: JT-118, JT-184]
- JT-191 (#191) Answer Q-42 rejected-role skill gaps [deps: JT-118, JT-184]
- JT-192 (#192) Answer Q-43 strongest and weakest signals [deps: JT-118, JT-184]
- JT-193 (#193) Answer Q-44 best-fit roles [deps: JT-118, JT-184]
- JT-194 (#194) Answer Q-45 next-week actions [deps: JT-118, JT-184]
- JT-195 (#195) Answer Q-46 search story [deps: JT-118, JT-184]

## Stage 14 (36 tickets)

- JT-121 (#121) Add metrics service foundation [deps: JT-046, JT-118, JT-120]
- JT-130 (#130) Add dashboard filter bar [deps: JT-044, JT-046, JT-118, JT-120]
- JT-136 (#136) Answer Q-01 lifetime applications [deps: JT-046, JT-118, JT-120]
- JT-137 (#137) Answer Q-02 applications by window [deps: JT-046, JT-118, JT-120]
- JT-138 (#138) Answer Q-03 distinct companies [deps: JT-046, JT-118, JT-120]
- JT-139 (#139) Answer Q-04 response versus silence [deps: JT-046, JT-118, JT-120]
- JT-140 (#140) Answer Q-05 rejection count [deps: JT-046, JT-118, JT-120]
- JT-141 (#141) Answer Q-06 ghosted count [deps: JT-046, JT-118, JT-120]
- JT-142 (#142) Answer Q-07 interview invitations [deps: JT-046, JT-118, JT-120]
- JT-143 (#143) Answer Q-08 offers received [deps: JT-046, JT-118, JT-120]
- JT-144 (#144) Answer Q-09 status of every application [deps: JT-046, JT-118, JT-120]
- JT-145 (#145) Answer Q-10 live applications [deps: JT-046, JT-118, JT-120]
- JT-146 (#146) Answer Q-11 overall response rate [deps: JT-046, JT-118, JT-120]
- JT-147 (#147) Answer Q-12 rejection rate [deps: JT-046, JT-118, JT-120]
- JT-148 (#148) Answer Q-13 ghost rate [deps: JT-046, JT-118, JT-120]
- JT-149 (#149) Answer Q-14 application to interview rate [deps: JT-046, JT-118, JT-120]
- JT-150 (#150) Answer Q-15 interview to offer rate [deps: JT-046, JT-118, JT-120]
- JT-151 (#151) Answer Q-16 full funnel [deps: JT-046, JT-118, JT-120]
- JT-152 (#152) Answer Q-17 time to first response [deps: JT-046, JT-118, JT-120]
- JT-153 (#153) Answer Q-18 time to rejection [deps: JT-046, JT-118, JT-120]
- JT-154 (#154) Answer Q-19 personal ghost threshold [deps: JT-046, JT-118, JT-120]
- JT-155 (#155) Answer Q-20 application volume trend [deps: JT-046, JT-118, JT-120]
- JT-156 (#156) Answer Q-21 response rate trend [deps: JT-046, JT-118, JT-120]
- JT-157 (#157) Answer Q-22 title volume and conversion [deps: JT-046, JT-118, JT-120]
- JT-158 (#158) Answer Q-23 best-converting titles [deps: JT-046, JT-118, JT-120]
- JT-159 (#159) Answer Q-24 company type conversion [deps: JT-046, JT-118, JT-120]
- JT-160 (#160) Answer Q-25 source outcomes [deps: JT-046, JT-118, JT-120]
- JT-161 (#161) Answer Q-26 salary band conversion [deps: JT-046, JT-118, JT-120]
- JT-162 (#162) Answer Q-27 work-mode conversion [deps: JT-046, JT-118, JT-120]
- JT-163 (#163) Answer Q-28 sponsorship availability count [deps: JT-046, JT-118, JT-120]
- JT-164 (#164) Answer Q-29 sponsorship conversion [deps: JT-046, JT-118, JT-120]
- JT-165 (#165) Answer Q-30 tech-stack conversion [deps: JT-046, JT-118, JT-120]
- JT-166 (#166) Answer Q-31 seniority conversion [deps: JT-046, JT-118, JT-120]
- JT-187 (#187) Add insights frontend page [deps: JT-027, JT-118, JT-186]
- JT-188 (#188) Add insight cost display [deps: JT-027, JT-118, JT-186]
- JT-196 (#196) Add insights grounding tests [deps: JT-118, JT-184, JT-185]

## Stage 15 (2 tickets)

- JT-122 (#122) Add metrics repository queries [deps: JT-046, JT-118, JT-120, JT-121]
- JT-123 (#123) Add metrics filter DTOs [deps: JT-046, JT-118, JT-120, JT-121]

## Stage 16 (15 tickets)

- JT-124 (#124) Add metrics summary endpoint [deps: JT-046, JT-118, JT-120, JT-122, JT-123]
- JT-125 (#125) Add metrics rates endpoint [deps: JT-046, JT-118, JT-120, JT-122, JT-123]
- JT-126 (#126) Add metrics funnel endpoint [deps: JT-046, JT-118, JT-120, JT-122, JT-123]
- JT-127 (#127) Add metrics timeseries endpoint [deps: JT-046, JT-118, JT-120, JT-122, JT-123]
- JT-128 (#128) Add metrics breakdown endpoint [deps: JT-046, JT-118, JT-120, JT-122, JT-123]
- JT-129 (#129) Add deterministic metric tests [deps: JT-046, JT-118, JT-120, JT-122]
- JT-135 (#135) Add metric reconciliation helpers [deps: JT-046, JT-118, JT-120, JT-122]
- JT-197 (#197) Add email chunking service [deps: JT-027, JT-062, JT-118, JT-122]
- JT-198 (#198) Add embedding provider interface [deps: JT-027, JT-118, JT-122]
- JT-202 (#202) Add structured query tool [deps: JT-027, JT-118, JT-122]
- JT-206 (#206) Add chat history endpoint [deps: JT-022, JT-027, JT-118, JT-122]
- JT-209 (#209) Answer Q-47 recruiter last-email recall [deps: JT-027, JT-118, JT-122]
- JT-210 (#210) Answer Q-48 rejection and sponsorship recall [deps: JT-027, JT-118, JT-122]
- JT-211 (#211) Answer Q-49 overdue follow-up recall [deps: JT-027, JT-118, JT-122]
- JT-212 (#212) Answer Q-50 free-form job-search chat [deps: JT-027, JT-118, JT-122]

## Stage 17 (24 tickets)

- JT-131 (#131) Add summary metric cards [deps: JT-046, JT-118, JT-120, JT-124]
- JT-132 (#132) Add rates and funnel widgets [deps: JT-046, JT-118, JT-120, JT-125, JT-126]
- JT-133 (#133) Add timeseries widgets [deps: JT-046, JT-118, JT-120, JT-127]
- JT-134 (#134) Add breakdown table and chart widgets [deps: JT-046, JT-118, JT-120, JT-128]
- JT-168 (#168) Add diagnostics service foundation [deps: JT-122, JT-129, JT-166]
- JT-172 (#172) Answer Q-32 common traits of successful applications [deps: JT-122, JT-129, JT-166]
- JT-173 (#173) Answer Q-33 common traits of rejected or ghosted applications [deps: JT-122, JT-129, JT-166]
- JT-174 (#174) Answer Q-34 strongest response correlate [deps: JT-122, JT-129, JT-166]
- JT-175 (#175) Answer Q-35 wasted-effort segments [deps: JT-122, JT-129, JT-166]
- JT-176 (#176) Answer Q-36 best ROI source [deps: JT-122, JT-129, JT-166]
- JT-177 (#177) Answer Q-37 sponsorship response impact [deps: JT-122, JT-129, JT-166]
- JT-178 (#178) Answer Q-38 selling versus dead-weight skills [deps: JT-122, JT-129, JT-166]
- JT-179 (#179) Answer Q-39 adjacent role suggestions [deps: JT-122, JT-129, JT-166]
- JT-199 (#199) Implement sqlite-vec chunk repository [deps: JT-018, JT-027, JT-118, JT-122, JT-197]
- JT-214 (#214) Answer Q-51 conversion probability [deps: JT-212]
- JT-215 (#215) Answer Q-52 market benchmark comparison [deps: JT-212]
- JT-216 (#216) Answer Q-53 currently open role prioritization [deps: JT-212]
- JT-217 (#217) Answer Q-54 company or recruiter activity check [deps: JT-212]
- JT-218 (#218) Add Outlook provider adapter [deps: JT-212]
- JT-219 (#219) Add IMAP provider adapter [deps: JT-212]
- JT-220 (#220) Add draft-writing workflow [deps: JT-212]
- JT-221 (#221) Add hosting-ready packaging [deps: JT-212]
- JT-222 (#222) Add mobile or voice access [deps: JT-212]
- JT-223 (#223) Add open-source hardening [deps: JT-212]

## Stage 18 (4 tickets)

- JT-167 (#167) Add dashboard smoke test [deps: JT-046, JT-118, JT-120, JT-131, JT-132, JT-133, JT-134]
- JT-169 (#169) Add diagnostics endpoint [deps: JT-122, JT-129, JT-166, JT-168]
- JT-180 (#180) Add diagnostics fixture tests [deps: JT-046, JT-122, JT-129, JT-166, JT-168]
- JT-200 (#200) Generate embeddings for job-related retained bodies [deps: JT-027, JT-118, JT-122, JT-198, JT-199]

## Stage 19 (3 tickets)

- JT-170 (#170) Add diagnostic comparison widgets [deps: JT-122, JT-129, JT-166, JT-169]
- JT-171 (#171) Add diagnostic explainability notes [deps: JT-122, JT-129, JT-166, JT-169]
- JT-201 (#201) Add semantic search tool [deps: JT-027, JT-118, JT-122, JT-199, JT-200]

## Stage 20 (1 tickets)

- JT-203 (#203) Add chat router graph [deps: JT-027, JT-118, JT-122, JT-201, JT-202]

## Stage 21 (1 tickets)

- JT-204 (#204) Add chat synthesis node [deps: JT-027, JT-118, JT-122, JT-203]

## Stage 22 (2 tickets)

- JT-205 (#205) Add SSE chat endpoint [deps: JT-027, JT-118, JT-122, JT-204]
- JT-208 (#208) Add chat grounding tests [deps: JT-027, JT-118, JT-122, JT-201, JT-202, JT-204]

## Stage 23 (1 tickets)

- JT-207 (#207) Add chat frontend [deps: JT-027, JT-118, JT-122, JT-205, JT-206]

## Stage 24 (1 tickets)

- JT-213 (#213) Add chat Playwright smoke test [deps: JT-027, JT-118, JT-122, JT-207]

## Mermaid

```mermaid
graph TD
  JT-002 --> JT-004
  JT-002 --> JT-005
  JT-002 --> JT-006
  JT-002 --> JT-007
  JT-002 --> JT-008
  JT-002 --> JT-009
  JT-008 --> JT-009
  JT-002 --> JT-010
  JT-002 --> JT-011
  JT-002 --> JT-012
  JT-002 --> JT-013
  JT-002 --> JT-014
  JT-013 --> JT-014
  JT-002 --> JT-015
  JT-013 --> JT-015
  JT-002 --> JT-016
  JT-002 --> JT-017
  JT-002 --> JT-018
  JT-017 --> JT-018
  JT-002 --> JT-019
  JT-017 --> JT-019
  JT-002 --> JT-020
  JT-019 --> JT-020
  JT-002 --> JT-021
  JT-020 --> JT-021
  JT-002 --> JT-022
  JT-020 --> JT-022
  JT-002 --> JT-023
  JT-002 --> JT-024
  JT-023 --> JT-024
  JT-002 --> JT-025
  JT-020 --> JT-025
  JT-002 --> JT-026
  JT-002 --> JT-027
  JT-002 --> JT-028
  JT-002 --> JT-029
  JT-002 --> JT-030
  JT-029 --> JT-030
  JT-002 --> JT-031
  JT-028 --> JT-031
  JT-002 --> JT-032
  JT-002 --> JT-033
  JT-002 --> JT-034
  JT-002 --> JT-035
  JT-002 --> JT-036
  JT-002 --> JT-037
  JT-036 --> JT-037
  JT-002 --> JT-038
  JT-033 --> JT-038
  JT-042 --> JT-038
  JT-002 --> JT-039
  JT-033 --> JT-039
  JT-042 --> JT-039
  JT-002 --> JT-040
  JT-033 --> JT-040
  JT-042 --> JT-040
  JT-002 --> JT-041
  JT-033 --> JT-041
  JT-042 --> JT-041
  JT-002 --> JT-042
  JT-002 --> JT-043
  JT-033 --> JT-043
  JT-002 --> JT-044
  JT-033 --> JT-044
  JT-002 --> JT-045
  JT-002 --> JT-046
  JT-045 --> JT-046
  JT-002 --> JT-047
  JT-002 --> JT-048
  JT-002 --> JT-049
  JT-002 --> JT-050
  JT-002 --> JT-051
  JT-002 --> JT-052
  JT-002 --> JT-053
  JT-002 --> JT-054
  JT-013 --> JT-055
  JT-017 --> JT-055
  JT-026 --> JT-055
  JT-013 --> JT-056
  JT-017 --> JT-056
  JT-026 --> JT-056
  JT-055 --> JT-056
  JT-013 --> JT-057
  JT-017 --> JT-057
  JT-026 --> JT-057
  JT-056 --> JT-057
  JT-013 --> JT-058
  JT-017 --> JT-058
  JT-026 --> JT-058
  JT-013 --> JT-059
  JT-017 --> JT-059
  JT-026 --> JT-059
  JT-013 --> JT-060
  JT-017 --> JT-060
  JT-026 --> JT-060
  JT-059 --> JT-060
  JT-013 --> JT-061
  JT-017 --> JT-061
  JT-026 --> JT-061
  JT-013 --> JT-062
  JT-017 --> JT-062
  JT-026 --> JT-062
  JT-061 --> JT-062
  JT-013 --> JT-063
  JT-017 --> JT-063
  JT-026 --> JT-063
  JT-013 --> JT-064
  JT-017 --> JT-064
  JT-026 --> JT-064
  JT-060 --> JT-064
  JT-062 --> JT-064
  JT-013 --> JT-065
  JT-017 --> JT-065
  JT-026 --> JT-065
  JT-013 --> JT-066
  JT-017 --> JT-066
  JT-026 --> JT-066
  JT-013 --> JT-067
  JT-017 --> JT-067
  JT-026 --> JT-067
  JT-066 --> JT-067
  JT-013 --> JT-068
  JT-017 --> JT-068
  JT-026 --> JT-068
  JT-013 --> JT-069
  JT-017 --> JT-069
  JT-026 --> JT-069
  JT-013 --> JT-070
  JT-017 --> JT-070
  JT-026 --> JT-070
  JT-069 --> JT-070
  JT-013 --> JT-071
  JT-017 --> JT-071
  JT-026 --> JT-071
  JT-013 --> JT-072
  JT-017 --> JT-072
  JT-026 --> JT-072
  JT-013 --> JT-073
  JT-017 --> JT-073
  JT-026 --> JT-073
  JT-013 --> JT-074
  JT-017 --> JT-074
  JT-026 --> JT-074
  JT-073 --> JT-074
  JT-013 --> JT-075
  JT-017 --> JT-075
  JT-026 --> JT-075
  JT-013 --> JT-076
  JT-017 --> JT-076
  JT-026 --> JT-076
  JT-074 --> JT-076
  JT-013 --> JT-077
  JT-017 --> JT-077
  JT-026 --> JT-077
  JT-074 --> JT-077
  JT-013 --> JT-078
  JT-017 --> JT-078
  JT-026 --> JT-078
  JT-055 --> JT-078
  JT-056 --> JT-078
  JT-013 --> JT-079
  JT-017 --> JT-079
  JT-026 --> JT-079
  JT-013 --> JT-080
  JT-017 --> JT-080
  JT-026 --> JT-080
  JT-027 --> JT-081
  JT-064 --> JT-081
  JT-073 --> JT-081
  JT-027 --> JT-082
  JT-064 --> JT-082
  JT-073 --> JT-082
  JT-027 --> JT-083
  JT-064 --> JT-083
  JT-073 --> JT-083
  JT-081 --> JT-083
  JT-082 --> JT-083
  JT-027 --> JT-084
  JT-064 --> JT-084
  JT-073 --> JT-084
  JT-027 --> JT-085
  JT-064 --> JT-085
  JT-073 --> JT-085
  JT-083 --> JT-085
  JT-099 --> JT-085
  JT-027 --> JT-086
  JT-064 --> JT-086
  JT-073 --> JT-086
  JT-027 --> JT-087
  JT-064 --> JT-087
  JT-073 --> JT-087
  JT-027 --> JT-088
  JT-064 --> JT-088
  JT-073 --> JT-088
  JT-027 --> JT-089
  JT-064 --> JT-089
  JT-073 --> JT-089
  JT-027 --> JT-090
  JT-064 --> JT-090
  JT-073 --> JT-090
  JT-027 --> JT-091
  JT-064 --> JT-091
  JT-073 --> JT-091
  JT-086 --> JT-091
  JT-087 --> JT-091
  JT-089 --> JT-091
  JT-090 --> JT-091
  JT-027 --> JT-092
  JT-064 --> JT-092
  JT-073 --> JT-092
  JT-091 --> JT-092
  JT-027 --> JT-093
  JT-064 --> JT-093
  JT-073 --> JT-093
  JT-027 --> JT-094
  JT-064 --> JT-094
  JT-073 --> JT-094
  JT-093 --> JT-094
  JT-027 --> JT-095
  JT-064 --> JT-095
  JT-073 --> JT-095
  JT-027 --> JT-096
  JT-064 --> JT-096
  JT-073 --> JT-096
  JT-027 --> JT-097
  JT-064 --> JT-097
  JT-073 --> JT-097
  JT-027 --> JT-098
  JT-064 --> JT-098
  JT-073 --> JT-098
  JT-027 --> JT-099
  JT-064 --> JT-099
  JT-073 --> JT-099
  JT-027 --> JT-100
  JT-064 --> JT-100
  JT-073 --> JT-100
  JT-099 --> JT-100
  JT-027 --> JT-101
  JT-064 --> JT-101
  JT-073 --> JT-101
  JT-100 --> JT-101
  JT-027 --> JT-102
  JT-064 --> JT-102
  JT-073 --> JT-102
  JT-027 --> JT-103
  JT-064 --> JT-103
  JT-073 --> JT-103
  JT-027 --> JT-104
  JT-064 --> JT-104
  JT-073 --> JT-104
  JT-102 --> JT-104
  JT-103 --> JT-104
  JT-027 --> JT-105
  JT-064 --> JT-105
  JT-073 --> JT-105
  JT-104 --> JT-105
  JT-027 --> JT-106
  JT-064 --> JT-106
  JT-073 --> JT-106
  JT-105 --> JT-106
  JT-027 --> JT-107
  JT-064 --> JT-107
  JT-073 --> JT-107
  JT-106 --> JT-107
  JT-027 --> JT-108
  JT-064 --> JT-108
  JT-073 --> JT-108
  JT-107 --> JT-108
  JT-027 --> JT-109
  JT-064 --> JT-109
  JT-073 --> JT-109
  JT-027 --> JT-110
  JT-064 --> JT-110
  JT-073 --> JT-110
  JT-105 --> JT-110
  JT-106 --> JT-110
  JT-108 --> JT-110
  JT-021 --> JT-111
  JT-027 --> JT-111
  JT-064 --> JT-111
  JT-073 --> JT-111
  JT-105 --> JT-111
  JT-021 --> JT-112
  JT-027 --> JT-112
  JT-064 --> JT-112
  JT-073 --> JT-112
  JT-105 --> JT-112
  JT-021 --> JT-113
  JT-027 --> JT-113
  JT-064 --> JT-113
  JT-073 --> JT-113
  JT-106 --> JT-113
  JT-027 --> JT-114
  JT-064 --> JT-114
  JT-073 --> JT-114
  JT-111 --> JT-114
  JT-112 --> JT-114
  JT-113 --> JT-114
  JT-027 --> JT-115
  JT-064 --> JT-115
  JT-073 --> JT-115
  JT-114 --> JT-115
  JT-027 --> JT-116
  JT-064 --> JT-116
  JT-073 --> JT-116
  JT-105 --> JT-116
  JT-027 --> JT-117
  JT-064 --> JT-117
  JT-073 --> JT-117
  JT-106 --> JT-117
  JT-027 --> JT-118
  JT-064 --> JT-118
  JT-073 --> JT-118
  JT-116 --> JT-118
  JT-027 --> JT-119
  JT-064 --> JT-119
  JT-073 --> JT-119
  JT-111 --> JT-119
  JT-112 --> JT-119
  JT-113 --> JT-119
  JT-027 --> JT-120
  JT-064 --> JT-120
  JT-073 --> JT-120
  JT-085 --> JT-120
  JT-091 --> JT-120
  JT-094 --> JT-120
  JT-110 --> JT-120
  JT-046 --> JT-121
  JT-118 --> JT-121
  JT-120 --> JT-121
  JT-046 --> JT-122
  JT-118 --> JT-122
  JT-120 --> JT-122
  JT-121 --> JT-122
  JT-046 --> JT-123
  JT-118 --> JT-123
  JT-120 --> JT-123
  JT-121 --> JT-123
  JT-046 --> JT-124
  JT-118 --> JT-124
  JT-120 --> JT-124
  JT-122 --> JT-124
  JT-123 --> JT-124
  JT-046 --> JT-125
  JT-118 --> JT-125
  JT-120 --> JT-125
  JT-122 --> JT-125
  JT-123 --> JT-125
  JT-046 --> JT-126
  JT-118 --> JT-126
  JT-120 --> JT-126
  JT-122 --> JT-126
  JT-123 --> JT-126
  JT-046 --> JT-127
  JT-118 --> JT-127
  JT-120 --> JT-127
  JT-122 --> JT-127
  JT-123 --> JT-127
  JT-046 --> JT-128
  JT-118 --> JT-128
  JT-120 --> JT-128
  JT-122 --> JT-128
  JT-123 --> JT-128
  JT-046 --> JT-129
  JT-118 --> JT-129
  JT-120 --> JT-129
  JT-122 --> JT-129
  JT-044 --> JT-130
  JT-046 --> JT-130
  JT-118 --> JT-130
  JT-120 --> JT-130
  JT-046 --> JT-131
  JT-118 --> JT-131
  JT-120 --> JT-131
  JT-124 --> JT-131
  JT-046 --> JT-132
  JT-118 --> JT-132
  JT-120 --> JT-132
  JT-125 --> JT-132
  JT-126 --> JT-132
  JT-046 --> JT-133
  JT-118 --> JT-133
  JT-120 --> JT-133
  JT-127 --> JT-133
  JT-046 --> JT-134
  JT-118 --> JT-134
  JT-120 --> JT-134
  JT-128 --> JT-134
  JT-046 --> JT-135
  JT-118 --> JT-135
  JT-120 --> JT-135
  JT-122 --> JT-135
  JT-046 --> JT-136
  JT-118 --> JT-136
  JT-120 --> JT-136
  JT-046 --> JT-137
  JT-118 --> JT-137
  JT-120 --> JT-137
  JT-046 --> JT-138
  JT-118 --> JT-138
  JT-120 --> JT-138
  JT-046 --> JT-139
  JT-118 --> JT-139
  JT-120 --> JT-139
  JT-046 --> JT-140
  JT-118 --> JT-140
  JT-120 --> JT-140
  JT-046 --> JT-141
  JT-118 --> JT-141
  JT-120 --> JT-141
  JT-046 --> JT-142
  JT-118 --> JT-142
  JT-120 --> JT-142
  JT-046 --> JT-143
  JT-118 --> JT-143
  JT-120 --> JT-143
  JT-046 --> JT-144
  JT-118 --> JT-144
  JT-120 --> JT-144
  JT-046 --> JT-145
  JT-118 --> JT-145
  JT-120 --> JT-145
  JT-046 --> JT-146
  JT-118 --> JT-146
  JT-120 --> JT-146
  JT-046 --> JT-147
  JT-118 --> JT-147
  JT-120 --> JT-147
  JT-046 --> JT-148
  JT-118 --> JT-148
  JT-120 --> JT-148
  JT-046 --> JT-149
  JT-118 --> JT-149
  JT-120 --> JT-149
  JT-046 --> JT-150
  JT-118 --> JT-150
  JT-120 --> JT-150
  JT-046 --> JT-151
  JT-118 --> JT-151
  JT-120 --> JT-151
  JT-046 --> JT-152
  JT-118 --> JT-152
  JT-120 --> JT-152
  JT-046 --> JT-153
  JT-118 --> JT-153
  JT-120 --> JT-153
  JT-046 --> JT-154
  JT-118 --> JT-154
  JT-120 --> JT-154
  JT-046 --> JT-155
  JT-118 --> JT-155
  JT-120 --> JT-155
  JT-046 --> JT-156
  JT-118 --> JT-156
  JT-120 --> JT-156
  JT-046 --> JT-157
  JT-118 --> JT-157
  JT-120 --> JT-157
  JT-046 --> JT-158
  JT-118 --> JT-158
  JT-120 --> JT-158
  JT-046 --> JT-159
  JT-118 --> JT-159
  JT-120 --> JT-159
  JT-046 --> JT-160
  JT-118 --> JT-160
  JT-120 --> JT-160
  JT-046 --> JT-161
  JT-118 --> JT-161
  JT-120 --> JT-161
  JT-046 --> JT-162
  JT-118 --> JT-162
  JT-120 --> JT-162
  JT-046 --> JT-163
  JT-118 --> JT-163
  JT-120 --> JT-163
  JT-046 --> JT-164
  JT-118 --> JT-164
  JT-120 --> JT-164
  JT-046 --> JT-165
  JT-118 --> JT-165
  JT-120 --> JT-165
  JT-046 --> JT-166
  JT-118 --> JT-166
  JT-120 --> JT-166
  JT-046 --> JT-167
  JT-118 --> JT-167
  JT-120 --> JT-167
  JT-131 --> JT-167
  JT-132 --> JT-167
  JT-133 --> JT-167
  JT-134 --> JT-167
  JT-122 --> JT-168
  JT-129 --> JT-168
  JT-166 --> JT-168
  JT-122 --> JT-169
  JT-129 --> JT-169
  JT-166 --> JT-169
  JT-168 --> JT-169
  JT-122 --> JT-170
  JT-129 --> JT-170
  JT-166 --> JT-170
  JT-169 --> JT-170
  JT-122 --> JT-171
  JT-129 --> JT-171
  JT-166 --> JT-171
  JT-169 --> JT-171
  JT-122 --> JT-172
  JT-129 --> JT-172
  JT-166 --> JT-172
  JT-122 --> JT-173
  JT-129 --> JT-173
  JT-166 --> JT-173
  JT-122 --> JT-174
  JT-129 --> JT-174
  JT-166 --> JT-174
  JT-122 --> JT-175
  JT-129 --> JT-175
  JT-166 --> JT-175
  JT-122 --> JT-176
  JT-129 --> JT-176
  JT-166 --> JT-176
  JT-122 --> JT-177
  JT-129 --> JT-177
  JT-166 --> JT-177
  JT-122 --> JT-178
  JT-129 --> JT-178
  JT-166 --> JT-178
  JT-122 --> JT-179
  JT-129 --> JT-179
  JT-166 --> JT-179
  JT-046 --> JT-180
  JT-122 --> JT-180
  JT-129 --> JT-180
  JT-166 --> JT-180
  JT-168 --> JT-180
  JT-020 --> JT-181
  JT-027 --> JT-181
  JT-118 --> JT-181
  JT-027 --> JT-182
  JT-118 --> JT-182
  JT-027 --> JT-183
  JT-118 --> JT-183
  JT-181 --> JT-183
  JT-182 --> JT-183
  JT-027 --> JT-184
  JT-086 --> JT-184
  JT-087 --> JT-184
  JT-118 --> JT-184
  JT-182 --> JT-184
  JT-027 --> JT-185
  JT-118 --> JT-185
  JT-184 --> JT-185
  JT-027 --> JT-186
  JT-118 --> JT-186
  JT-181 --> JT-186
  JT-184 --> JT-186
  JT-027 --> JT-187
  JT-118 --> JT-187
  JT-186 --> JT-187
  JT-027 --> JT-188
  JT-118 --> JT-188
  JT-186 --> JT-188
  JT-118 --> JT-189
  JT-184 --> JT-189
  JT-118 --> JT-190
  JT-184 --> JT-190
  JT-118 --> JT-191
  JT-184 --> JT-191
  JT-118 --> JT-192
  JT-184 --> JT-192
  JT-118 --> JT-193
  JT-184 --> JT-193
  JT-118 --> JT-194
  JT-184 --> JT-194
  JT-118 --> JT-195
  JT-184 --> JT-195
  JT-118 --> JT-196
  JT-184 --> JT-196
  JT-185 --> JT-196
  JT-027 --> JT-197
  JT-062 --> JT-197
  JT-118 --> JT-197
  JT-122 --> JT-197
  JT-027 --> JT-198
  JT-118 --> JT-198
  JT-122 --> JT-198
  JT-018 --> JT-199
  JT-027 --> JT-199
  JT-118 --> JT-199
  JT-122 --> JT-199
  JT-197 --> JT-199
  JT-027 --> JT-200
  JT-118 --> JT-200
  JT-122 --> JT-200
  JT-198 --> JT-200
  JT-199 --> JT-200
  JT-027 --> JT-201
  JT-118 --> JT-201
  JT-122 --> JT-201
  JT-199 --> JT-201
  JT-200 --> JT-201
  JT-027 --> JT-202
  JT-118 --> JT-202
  JT-122 --> JT-202
  JT-027 --> JT-203
  JT-118 --> JT-203
  JT-122 --> JT-203
  JT-201 --> JT-203
  JT-202 --> JT-203
  JT-027 --> JT-204
  JT-118 --> JT-204
  JT-122 --> JT-204
  JT-203 --> JT-204
  JT-027 --> JT-205
  JT-118 --> JT-205
  JT-122 --> JT-205
  JT-204 --> JT-205
  JT-022 --> JT-206
  JT-027 --> JT-206
  JT-118 --> JT-206
  JT-122 --> JT-206
  JT-027 --> JT-207
  JT-118 --> JT-207
  JT-122 --> JT-207
  JT-205 --> JT-207
  JT-206 --> JT-207
  JT-027 --> JT-208
  JT-118 --> JT-208
  JT-122 --> JT-208
  JT-201 --> JT-208
  JT-202 --> JT-208
  JT-204 --> JT-208
  JT-027 --> JT-209
  JT-118 --> JT-209
  JT-122 --> JT-209
  JT-027 --> JT-210
  JT-118 --> JT-210
  JT-122 --> JT-210
  JT-027 --> JT-211
  JT-118 --> JT-211
  JT-122 --> JT-211
  JT-027 --> JT-212
  JT-118 --> JT-212
  JT-122 --> JT-212
  JT-027 --> JT-213
  JT-118 --> JT-213
  JT-122 --> JT-213
  JT-207 --> JT-213
  JT-212 --> JT-214
  JT-212 --> JT-215
  JT-212 --> JT-216
  JT-212 --> JT-217
  JT-212 --> JT-218
  JT-212 --> JT-219
  JT-212 --> JT-220
  JT-212 --> JT-221
  JT-212 --> JT-222
  JT-212 --> JT-223
```
