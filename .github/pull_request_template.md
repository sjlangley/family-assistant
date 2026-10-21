<!--
A reviewer, human or LLM, reads this before your diff.

The PR title becomes the commit subject on the trunk: Conventional Commits,
lowercase, 72 characters or fewer. release-please reads it: see "Commits and
Pull Requests" in AI_AGENT_GUIDELINES.md for which types cut a release. The
description becomes the commit
body, so everything below is permanent. Delete these comments before merging;
they are copied into the commit too.
-->

## What

<!--
One paragraph, readable without opening the diff. Add why the change was needed,
and anything about the approach that would surprise a reviewer, where those are
not already obvious from the diff or the linked issue. A typo fix needs a
sentence; a change of approach needs the reasoning.
-->

## Testing

<!--
How you verified this. "Tested manually" is not enough. Say what you tested and
how. Write "None" if you did not verify it, because an empty field reads as an
oversight rather than a decision.
-->

Fixes: #

<!--
Fixes closes the issue on merge. Use Refs: instead where this is one of several
PRs against the same issue, so only the last one closes it.
-->
