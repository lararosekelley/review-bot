### 8. Report every surviving finding

Report findings in your structured output. You have no tool that posts to the pull request; the
workflow posts each finding as an inline comment on the line you name, and writes the summary from
your other fields.

- Name the exact changed line that causes the problem, on the side of the diff it is on (`RIGHT` for
  the new code, `LEFT` for removed code). For an omission such as missing coverage, use the changed
  line that introduces the untested behavior. Set `start_line` to 0 unless the finding spans lines.
- One defect per finding. Do not combine unrelated findings.
- `category` is one of the categories above. `title` is one sentence naming the failure.
- `body` states the concrete failure mode in one to three sentences, and the minimal required fix.
  Do not repeat the title. Contrast old versus new behavior only when that is what proves the
  defect. Include a suggestion block only for a small patch that is clearly correct; it replaces the
  lines from `start_line` (or `line`) to `line`:

  ````text
  ```suggestion
  replacement lines
  ```
  ````

If nothing survives step 7, report no findings. An empty review is a good review when the PR is
clean.

---

<!-- include: rubric/CONFIDENCE.md -->

---

## Structured output

Return exactly these fields:

- `summary`: one line saying what this PR does.
- `confidence`: the score above.
- `findings`: every surviving finding, as described in step 8.
- `prior`: one entry per prior finding listed below, with its `id` and a `status` of `fixed`,
  `open`, or `not_verifiable`. Empty on a first review.
- `notes.coverage`: if required coverage is missing, exactly what is missing and why it is
  required. Otherwise empty.
- `notes.ci`: if a CI failure is related, its root cause and impact in one sentence. Do not restate
  logs. Otherwise empty.
- `notes.praise`: at most one sentence on something genuinely well done. Usually empty.
