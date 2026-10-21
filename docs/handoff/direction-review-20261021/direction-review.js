export const meta = {
  name: 'direction-review',
  description: 'Five strategists propose how the research direction should change; two adversarial critics check each proposal against the on-disk evidence; one synthesizer writes the owner recommendation; one final checker audits it',
  phases: [
    { title: 'Propose', detail: 'five independent lenses, each a written proposal + structured summary', model: 'opus' },
    { title: 'Refute', detail: 'two critics per proposal: evidence fidelity, feasibility/cost/protocol', model: 'opus' },
    { title: 'Synthesize', detail: 'one plain-Chinese recommendation for the owner', model: 'opus' },
    { title: 'Check', detail: 'final audit of the synthesis against the critiques', model: 'opus' },
  ],
}

const S = args.scratch
const REPO = args.repo
const BRIEF = `${S}/direction/brief.md`

const LENSES = [
  { key: 'instrument', title: '量尺优先（先把测量仪器修到能分辨规则大小的效果，再谈方法）',
    angle: `Take "the measuring instrument is the bottleneck" as the organizing principle. Decide what the instrument must become (scoring fixes: JSON answers accepted and format errors recorded separately; same-session interleaved arms; request spacing; item counts and which benches can detect what; version-level vs rule-level units; statistical criterion per D8/D11/D1) BEFORE any further method work, and say precisely which experiments then become answerable. Say what to do if, after the instrument is fixed, the learned effect over the task card is still ~0.` },
  { key: 'method', title: '方法优先（协同进化的机制本身应该变成什么）',
    angle: `Objective 1 is "co-evolution: skill evolution + verifier-side (coding rubric) evolution". Given the evidence (rules too small to detect, version-level acceptance works in the D1 pilot, conditional rules per D13, executable skills per D3, generated tasks saturated per D6/D12/E1/E9/E5, a "make it harder" examiner invents loopholes per E10, model-written checkers ≈ guessing per E1), decide what the unit of evolution should be, what the verifier side can honestly evolve (if anything), whether v4 as specified is the right next build or should be narrowed/replaced, and which single mechanism experiment is most informative next.` },
  { key: 'transfer', title: '泛化评测优先（在一个 bench 上进化、在其余 bench 上评测，怎样才测得出来）',
    angle: `Objective 2 is generalization: evolve on one bench, evaluate on the others, without a validation set. The evidence says registered "similar" pairs do not predict transfer (E4), format conflicts cause −8..−27 negative transfer (E4/E9), serving-mode drift is 22–24 points across sessions (D11/D12/E2), the v3 similar-benchmark check never ran (D12), and small pools (OfficeQA 74, ALFWorld 57) only detect ≥9–12 points. Design the transfer evaluation that is detectable and honest: which bench to evolve on, which to evaluate on, what counts as transfer, which controls (task card, placebo, identical-copy alarm), what "no drop on dissimilar" means operationally, and how to keep "no validation set" true (D12/E9 warn that screening rules on another bench's training items is a validation set in disguise).` },
  { key: 'paper', title: '论文优先（现有证据能支持什么论文，补哪几个实验就够）',
    angle: `Decide what claim the project can publish in 6–8 weeks given the actual evidence (D10 proposes a "measurement + negative result" paper; v8–v11 found gains ≈ generic-instruction effects; v3 accepted 0 rules; cal-1 calibrates the gate; the exploration found scoring artefacts and serving-mode drift). State the candidate claims, which experiments are necessary and sufficient for each, which existing results can be reused as-is, what would turn the story positive, and the honest venue/positioning. Do not propose a positive-method paper unless you can name the experiment whose result would support it and its detection power.` },
  { key: 'stoploss', title: '止损与反方（最保守的路线：该停什么、最便宜的决定性实验是什么）',
    angle: `Be the devil's advocate. Challenge the dominant story "the instrument is the bottleneck" — maybe the true effect of learned rules over a good task card is ~0 and no instrument will find it; note D9's critic said the 0–3 point headroom was not measured with a "card + one rule" arm, and v8–v11 already found learning ≈ generic instruction. Audit sunk cost (v4's 24-item plan, the five-bench harness, generated-task machinery). Propose the cheapest decisive experiment that settles "is there anything to learn beyond a good instruction on these benches", with item counts and cost, and the stop rules. Say explicitly which lines should be stopped outright (including whether v4 should be implemented), and what the owner should do instead if the answer is "nothing to learn here".` },
]

const PROPOSAL_SCHEMA = {
  type: 'object',
  properties: {
    lens: { type: 'string' },
    file: { type: 'string', description: 'absolute path of the proposal file you wrote' },
    headline_cn: { type: 'string', description: 'one plain-Chinese sentence: the direction change you recommend' },
    diagnosis: { type: 'string', description: 'what the evidence says the real problem is (English or Chinese, ≤ 200 words)' },
    stop: { type: 'array', items: { type: 'string' } },
    keep: { type: 'array', items: { type: 'string' } },
    change: { type: 'array', items: { type: 'string' } },
    sequence: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, purpose: { type: 'string' }, design: { type: 'string' },
      items: { type: 'string', description: 'which pools / how many items / runs' },
      cost_tokens: { type: 'string', description: 'anchored estimate with the anchor named' },
      decision_rule: { type: 'string' }, pivot_condition: { type: 'string', description: 'what result would make us change course' },
    }, required: ['name', 'purpose', 'design', 'items', 'cost_tokens', 'decision_rule', 'pivot_condition'] } },
    claims: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, source: { type: 'string', description: 'file path + line/section/JSON field' },
    }, required: ['claim', 'source'] }, description: 'every factual claim the proposal rests on' },
    risks: { type: 'array', items: { type: 'string' } },
    summary_cn: { type: 'string', description: 'plain-Chinese summary for the owner, ≤ 400 Chinese characters, every code name explained' },
  },
  required: ['lens', 'file', 'headline_cn', 'diagnosis', 'stop', 'keep', 'change', 'sequence', 'claims', 'risks', 'summary_cn'],
}

const CRITIQUE_SCHEMA = {
  type: 'object',
  properties: {
    lens: { type: 'string' }, critic: { type: 'string' },
    verdict: { type: 'string', enum: ['sound', 'needs_revision', 'rejected'] },
    refuted_claims: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, why: { type: 'string' }, source: { type: 'string' },
    }, required: ['claim', 'why', 'source'] } },
    confirmed_claims: { type: 'array', items: { type: 'string' } },
    feasibility_issues: { type: 'array', items: { type: 'string' } },
    corrections_cn: { type: 'array', items: { type: 'string' }, description: 'plain-Chinese corrections the synthesizer must apply' },
    what_survives_cn: { type: 'string', description: 'plain Chinese: which parts of the proposal still stand after your check' },
    file: { type: 'string', description: 'absolute path of the critique file you wrote' },
  },
  required: ['lens', 'critic', 'verdict', 'refuted_claims', 'confirmed_claims', 'feasibility_issues', 'corrections_cn', 'what_survives_cn', 'file'],
}

const SYNTH_SCHEMA = {
  type: 'object',
  properties: {
    file: { type: 'string' },
    summary_cn: { type: 'string' },
    stop_cn: { type: 'array', items: { type: 'string' } },
    keep_cn: { type: 'array', items: { type: 'string' } },
    change_cn: { type: 'array', items: { type: 'string' } },
    sequence_cn: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, purpose: { type: 'string' }, cost_tokens: { type: 'string' }, decision_rule: { type: 'string' },
    }, required: ['name', 'purpose', 'cost_tokens', 'decision_rule'] } },
    disagreements_cn: { type: 'array', items: { type: 'string' } },
    owner_decisions_cn: { type: 'array', items: { type: 'string' } },
  },
  required: ['file', 'summary_cn', 'stop_cn', 'keep_cn', 'change_cn', 'sequence_cn', 'disagreements_cn', 'owner_decisions_cn'],
}

const CHECK_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    corrections: { type: 'array', items: { type: 'object', properties: {
      where: { type: 'string' }, problem: { type: 'string' }, fix_cn: { type: 'string' }, source: { type: 'string' },
    }, required: ['where', 'problem', 'fix_cn', 'source'] } },
    missing_cn: { type: 'array', items: { type: 'string' } },
    file: { type: 'string' },
  },
  required: ['ok', 'corrections', 'missing_cn', 'file'],
}

const common = `Repository root: ${REPO} (read-only; use absolute paths). Scratchpad: ${S}.
FIRST read the brief ${BRIEF} in full and obey its rules (read-only, no API calls, no experiments, no SSH, never open test pools, every factual claim carries a file source, plain Chinese for anything addressed to the owner).
Then read, in this order: ${REPO}/docs/handoff/overnight-report-20261021.md (all of it), ${REPO}/docs/handoff/feasibility-exploration-20261021-cn.md, ${REPO}/docs/handoff/cal1-registration-20261020.md, the 10/19–10/21 ledger entries in ${REPO}/docs/results-and-lessons.md (grep for '^\\*\\*10/19', '^\\*\\*10/20', '^\\*\\*10/21', and the '10/12' entry about generic-instruction controls), and the per-direction files under ${REPO}/docs/handoff/feasibility-20261021/<ID>/ (result.json and critic-result.json for EVERY direction; report.md where you need the detail). Also skim ${REPO}/docs/handoff/v4-plans-20261021/spec.md (§ list of B1–B17/P1–P7) and ${REPO}/docs/project-status.md §0/§4/§5.`

phase('Propose')
const proposals = await pipeline(LENSES,
  (lens) => agent(`You are one of five independent research strategists. Your lens: ${lens.title}.
${common}

Your angle: ${lens.angle}

Deliverable: write ${S}/direction/proposals/${lens.key}.md (≤ 3,000 words; English or Chinese for the body, but include a plain-Chinese 'summary_cn' section at the end for the owner, ≤ 400 Chinese characters, explaining every code name on first use). Structure:
1. 诊断 Diagnosis: what the evidence actually shows the problem is (with sources).
2. 停 / 留 / 改 Stop / Keep / Change: concrete lines of work, each justified by a cited result.
3. 接下来的实验序列 Sequence: 3–5 experiments for the next 4–6 weeks, in order. For each: purpose, design, pools and item counts (use the real pool sizes from the v6 registration table), runs, cost in tokens anchored to measured actuals (cal-1 ≈3.1k tokens/solver call; v3 ≈139M; the pilots' own cost fields), decision rule fixed in advance, and the pivot condition (what result changes course).
4. 如何服务两个目标 How this serves objective 1 (co-evolution of skill + verifier rubric) and objective 2 (evolve on one bench, evaluate on the others, no validation set). Be explicit if your lens says one objective should be deprioritized and why.
5. 风险与证伪 Risks and what would falsify your proposal.
6. 事实清单 Claims table: every factual claim with file path + line/section/field.
Rules: do not restate a claim the critics already refuted (brief lists the main ones) as if it were true; distinguish pilot/replay/fixture from method-effect evidence; propose nothing that reads test pools or that uses another bench's training items as a selection gate (that is a validation set in disguise). Then return the structured summary.`,
    { label: `propose:${lens.key}`, phase: 'Propose', schema: PROPOSAL_SCHEMA, model: 'opus' }),
  (proposal, lens) => {
    if (!proposal) return null
    return parallel([
      () => agent(`You are an adversarial EVIDENCE-FIDELITY critic. A strategist (lens: ${lens.title}) wrote a direction proposal at ${proposal.file}. Your job is to try to REFUTE it using the on-disk evidence, not opinion.
${common}

Procedure: (1) read the proposal; (2) for EVERY entry in its claims table and every number in its text, open the cited source and check it (quote the line or field); (3) check whether the proposal rests on any claim a critic-result.json already refuted (e.g. the E4 '+7 generic gain', the 'placebo −9.8', D9's '0–3 points headroom', D3's harness-dependent gain, E9/E10 item counts) or misreads cal-1 (n=11 passage 75.8%, bridges ≈0, placebo −0.098/+0.036) or v3 (0 rules accepted, 30/194 churn, dead panel items, forward path never ran); (4) check that it does not present pilot/replay/fixture results as method-effect evidence. Default to refuted=true when a claim has no checkable source. Write your critique to ${S}/direction/critiques/${lens.key}-evidence.md (refuted claims with the exact source text, confirmed claims, what survives) and return the structured result. corrections_cn must be plain Chinese the synthesizer can apply verbatim.`,
        { label: `refute-evidence:${lens.key}`, phase: 'Refute', schema: CRITIQUE_SCHEMA, model: 'opus' }),
      () => agent(`You are an adversarial FEASIBILITY / COST / PROTOCOL critic. A strategist (lens: ${lens.title}) wrote a direction proposal at ${proposal.file}. Your job is to try to REFUTE its plan, not its prose.
${common}

Check every experiment in its sequence: (a) item counts against the real training pools (v6 registration table: SearchQA 600, OfficeQA 74, LiveMath 283, ALFWorld 57, SpreadsheetBench as registered) and against the detection-power numbers measured by D1/D5/D8/D11/E5 (what minimal effect each pool can detect, and how many items a +2/+3/+5 point effect needs); (b) cost against measured actuals (cal-1 27.48M tokens for 8,800 calls; v3 ≈139M; the pilots' own cost fields) — recompute, do not accept the proposal's numbers; (c) protocol: it must never read test pools, must not smuggle in a validation set (screening or selecting rules on another bench's training items counts), must respect frozen protocols (new behaviour = new version/output dir), and must keep the owner's two objectives in view; (d) duplication: does it repeat an experiment already done (v8–v11 generic-instruction controls, cal-1, D/E pilots) or already refuted; (e) time: is it realistic in 1–3 overnight sessions with the known workflow limits (agents <45 min, 5-hour usage limits)? (f) decision rules: are they fixed in advance and can the stated item counts actually reach them? Write your critique to ${S}/direction/critiques/${lens.key}-feasibility.md and return the structured result. corrections_cn must be plain Chinese the synthesizer can apply verbatim.`,
        { label: `refute-feasibility:${lens.key}`, phase: 'Refute', schema: CRITIQUE_SCHEMA, model: 'opus' }),
    ]).then(cs => ({ lens: lens.key, title: lens.title, proposal, critiques: cs.filter(Boolean) }))
  }
)

const done = proposals.filter(Boolean)
log(`proposals with critiques: ${done.length}/${LENSES.length}; critiques: ${done.reduce((n, d) => n + d.critiques.length, 0)}`)

phase('Synthesize')
const index = done.map(d => `- ${d.title} (${d.lens}): proposal ${d.proposal.file}; critiques ${d.critiques.map(c => c.file).join(', ')}; verdicts ${d.critiques.map(c => c.verdict).join('/')}`).join('\n')
const synthesis = await agent(`You are the synthesizer. Five strategists proposed how the project's research direction should change, and two adversarial critics checked each proposal against the on-disk evidence. Produce ONE recommendation for the owner.
${common}

Then read ALL proposals and ALL critiques:
${index}

Write ${S}/direction/synthesis.md in plain Chinese for the owner (they cannot follow jargon; explain every code name the first time it appears: v3, v4, cal-1, C1, I-ds/E-ds, D1…D14, E1…E10, task card 任务卡, placebo 安慰剂, serving-mode drift 时段漂移, etc.). Structure, in this order:
1. 一句话结论（方向应该怎么改）。
2. 证据说明了什么：3–6 条，每条一两句话，每条标注来源文件。
3. 方向调整：停什么、留什么、改什么（每条一两句，给理由与来源）。
4. 接下来按顺序做的 3–5 件事：每件写目的、做法、用哪个训练池多少题跑几遍、费用（按实测锚定）、事先定好的判定规则、什么结果会让我们再改方向。
5. 两个目标怎么办：目标一（协同进化：Skill 进化 + 验证端评分细则进化）和目标二（在一个 bench 上进化、其余 bench 上评测、不用验证集）各自诚实的现状与建议。
6. 五位策略员的分歧与取舍：哪些地方他们不一致，综合时怎么取舍、为什么。
7. 需要负责人决定的事。
8. 事实来源表：本文用到的每条事实 → 文件路径（行/段/字段）。
Hard rules: never include a claim a critic refuted unless you state the refutation; prefer claims both critics confirmed; keep costs anchored and recomputed; keep the two objectives explicit; no dressing up of negative results; ≤ 3,500 Chinese characters for sections 1–7 (the source table may be longer). Then return the structured summary (all fields in plain Chinese).`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA, model: 'opus' })

phase('Check')
const check = synthesis ? await agent(`You are the final auditor. Read ${synthesis.file} (the owner recommendation) and then EVERY critique file under ${S}/direction/critiques/ and every proposal under ${S}/direction/proposals/.
${common}

Find: (1) any statement in the synthesis that a critic refuted or that contradicts a cited source (open the source and quote it); (2) any cost or item count that is not anchored or is miscomputed (recompute from cal-1 ≈3.1k tokens/call, v3 ≈139M, pool sizes 600/74/283/57/SpreadsheetBench); (3) any place where a negative result is softened or a pilot is presented as method-effect evidence; (4) anything the synthesis dropped that a majority of proposals or critics considered essential, including either of the owner's two objectives; (5) any jargon or code name used without explanation for the owner. Write ${S}/direction/check.md and return the structured list of corrections (fix_cn in plain Chinese, ready to apply) and missing items. ok=true only if there is nothing to correct.`,
  { label: 'final-check', phase: 'Check', schema: CHECK_SCHEMA, model: 'opus' }) : null

return { proposals: done.map(d => ({ lens: d.lens, headline_cn: d.proposal.headline_cn, file: d.proposal.file, verdicts: d.critiques.map(c => ({ critic: c.critic, verdict: c.verdict, file: c.file })) })), synthesis, check }