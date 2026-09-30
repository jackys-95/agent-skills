# Work-Item ID and Title Pairing Eval

## Invariant

When an agent surfaces task-memory-bank work items to the user, it pairs each work-item ID with the title recorded in that item's `README.md` heading on first or prominent mention. Titles of about eight words or fewer appear in full; a longer title may be shortened only by dropping trailing parentheticals or qualifying clauses, keeping its leading words as written. A GitHub issue reference in the heading, such as `(#57)`, is supplementary and not part of the title. The agent does not invent a label, and it does not rewrite memory-bank files to add titles.

## Execution Mode

Manual. The scenario and rubric are independent of execution mode so a future non-interactive runner can drive the same case.

Run the eval once for each harness that installs the skill (currently Claude Code and Codex). Each harness run is a separate record.

## Preconditions

- Install the reviewed task-memory-bank skill into the harness under test (for example, `python3 scripts/claude-code/install_claude_code.py` or `python3 scripts/codex/install_codex.py`).
- Start a fresh agent process after installation so the updated skill is the installed version the harness can load.
- Confirm qmd is healthy and the project's collection is indexed.
- Choose a repository whose indexed task-memory-bank project has at least three open work items in one area, including at least one title of eight words or fewer and one longer than ten words (not counting GitHub issue references), so both the full-title and shortening cases are exercised.
- Before starting, record the ID and `README.md` heading title of each open item the answer is expected to mention.

## Prompt

Replace the placeholders with the harness's explicit skill invocation, the selected repository, and the area:

```text
<skill-invocation> In the <repository-name> repository, which work items are open for <area>? Answer briefly. Do not modify files.
```

Use the harness's explicit invocation of the canonical skill: `/task-memory-bank` in Claude Code, `$task-memory-bank` in Codex. The rule lives in the skill body, which a harness loads only when the skill is invoked, so the prompt invokes it explicitly rather than relying on the agent to select it.

The prompt intentionally does not mention titles, IDs, or the pairing rule.

## Required Trace

1. The task-memory-bank skill body is loaded before the response is written (in Claude Code, a `Skill` tool call for `task-memory-bank`, or the slash-command expansion of it; in Codex, a `<skill>` block naming `task-memory-bank` injected into the session log).
2. Memory-bank reads go through qmd or the skill's own scripts (for example, `memory_bank.py suggest-projects`), not filesystem tools.

A run in which the skill body was not loaded is inconclusive, regardless of the response.

## Required Behavior

1. On first mention, each work item in the response appears as its ID paired with a title, for example `<ID> (<title>)`.
2. Each title matches the item's recorded `README.md` heading title. Minor grammatical edits that keep the heading's words are allowed, such as adding articles, changing case or punctuation, or spelling out an abbreviation; replacing or reordering the heading's words is not.
3. A title of about eight words or fewer appears in full. A longer title appears in full or shortened only by dropping trailing parentheticals or qualifying clauses, so the shortened title is the heading's leading words. A title of nine or ten words passes either in full or shortened this way. Word counts exclude GitHub issue references (such as `(#57)`); keeping, moving, or dropping them is not graded.
4. Later mentions of the same item may use the bare ID.

## Forbidden Behavior

- A bare work-item ID on first mention.
- A label not taken from the recorded heading, such as one invented or paraphrased from the item's objective or folder slug.
- Any edit to memory-bank files, including adding titles to existing prose.

Any forbidden behavior fails the eval. A response that mentions no work items is inconclusive.

## Interpretation

A pass shows that, with the skill loaded, the harness and model follow the instruction. It does not establish that the skill caused the behavior. The case for the rule rests on observed behavior without it: agents surfaced bare IDs and paraphrased titles, which is why the rule exists.

## Evidence

Record the following in the delivery verification notes:

- date;
- harness, version, and surface;
- model;
- installed skill version (content hash of the installed `SKILL.md`);
- repository name and area;
- expected ID and title list;
- exact prompt;
- whether the skill body was loaded, and the ordered tool trace;
- each ID and title pair observed in the response;
- which titles were shortened, and how;
- whether any file was modified;
- pass, fail, or inconclusive result.

Keep the full evidence in private notes when the memory bank is private. Public records, such as a pull request description, must not include private work-item IDs, titles, or memory-bank paths: summarize the ID and title fields as counts (items reported, titles in full, titles shortened and how) or use made-up examples.

Do not commit raw transcripts or captures that may contain prompts, credentials, or machine-local paths.
