# Documentary reference context — candidate 2.6.5

This candidate corrects the next document sent to the creative writer. It has not
been activated or qualified with a new Qwen response. The received 2.6.3 native
result, active 2.6.4 sources and historical parent 928 remain separate evidence.

The executed 2.6.4 input builder still assigned the first retained reference to
shots 1 and 2 and the second to shot 3. This appeared in three places: each
`shot_plan.retained_reference`, the USER instruction “Preserve supplied bindings”,
and the SYSTEM instruction “Preserve the supplied shot_plan bindings”. These
were prospective messages reconstructed from the active functions and dated
received input, not the original request consumed for parent 928.

The candidate removes the per-shot reference from the writer-facing plan and
both binding instructions. The complete retained-reference catalogue stays in
the USER document, with the same order, IDs, returned values and evidence
pointers. It is documentary context, with no required artistic use and no
automatic reference for the whole brief. Synopsis, themes, canonical certainty,
constraints, shot purposes, timing, assets and output schema stay the same.

The native response schema asks for text fields, not reference IDs. The core
still attaches its existing positional source links after consuming that text;
their removal from the writer input does **not** remove every positional link in
the product. The existing `limitations` array now states that these links are
compatibility provenance, not instructions or evidence that a reference caused
a scene. The deterministic validator checks source identity and constraints; it
does not establish artistic causality. The verifier receives that limitation in
its existing full context, and its unchanged SYSTEM checks lineage per shot,
not by shot number.

Focused checks execute the real Role2 callback path, default context provider,
native message builder, response schema and deterministic output checks. A
predetermined synthetic text response with no reference fields is consumed; its
compatibility links are added by the core, without a model or cultural-quality
verdict. Reordering the synthetic catalogue changes no shot directive. Existing
certainty, sound-off and text-length checks remain in force.

Run these checks from the repository root:

```sh
python3 -B -m unittest discover -s tests -p test_scaffold_input.py -v
python3 -B -m unittest discover -s tests -p test_reference_context.py -v
```

`comparisons/capture_reference_context.py` rebuilds the complete SYSTEM and USER
messages before and after, checks the frozen source and dated-input hashes, and
requires equality with the first preserved observation. It writes captures only
outside the source checkout because the dated cultural context is not a public
fixture. The only payload differences allowed are `creative_contract` and the
four removed `retained_reference` fields. The SYSTEM changes only the reference
instruction. This proves an input-contract correction, not better creative
output or a useful cultural contribution. No new Qloo call, model response,
family, persistent quota, runner profile, service, pin, frontend or historical
output is part of this change. Previous comparison packets and scores are not
rewritten.
