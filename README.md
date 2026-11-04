# matrix-reach

**Expand a GitHub Actions matrix exactly, then audit what the YAML hides.** The tool
reproduces GitHub's documented order — cartesian product, `exclude`, then sequential
`include` augmentation/new-combination — and proves each of its 10 rules with a
mutation fixture before it reports anything.

Upstream: https://github.com/actions/starter-workflows (corpus), plus real workflows
from `pandas-dev/pandas`, `django/django`, `python/cpython`.

## What it does

```bash
python -m matrix_reach.cli --self-test          # 10/10 rules proven, exit 0
python -m matrix_reach.cli examples/            # scan a directory
python -m matrix_reach.cli --json examples/     # machine-readable
```

Exit codes: **0** no errors (notes allowed), **1** errors, **2** a rule failed its
mutation proof or the input was unusable.

Reported rules:

| rule | meaning | severity |
|---|---|---|
| MR001 | duplicate combination after expansion | error |
| MR002 | `exclude` matches no combination | error |
| MR003 | `include` value is not in the axis (creates an extra combo) | note |
| MR004 | `include` matches no base combo (creates an extra combo) | note |
| MR005 | `exclude` key is not an axis | error |
| MR006 | `matrix.<key>` referenced but never defined | error |
| MR007 | `max-parallel` exceeds the combination count | note |
| MR008 | `fail-fast` is not a boolean | error |
| MR010 | `include`/`exclude` is not a list of mappings | error |
| MR011 | `exclude` value is not in the axis (can never match) | error |

规则编号**没有 MR009**：`grep -rn MR009 matrix_reach/ tests/` 为 0 命中（本次这行说明是仓库里唯一一次提到它），
它是一个未使用的编号。对外规则就是上表这 10 条（MR001–MR008、MR010、MR011）；`--self-test` 也正好覆盖这 10 条。

**Severity matters.** MR003/MR004 are how maintainers intentionally add one-off jobs
(pandas' `environment: downstream`, CPython's `sanitizer: ASan`). Calling those errors
would be noise. They are notes; only provable contradictions are errors.

### Expression matrices are skipped, not guessed

If any matrix value contains `${{ ... }}` (for example
`os: ${{ fromJSON(needs.ctx.outputs.matrix) }}`), the job is marked `skipped` with a
reason. Static expansion of an expression is unsound, and a tool that pretends
otherwise manufactures findings. That is why the CPython `build.yml` expression job
produces no verdict.

## Measured corpus result

Two corpora, scanned on 2026-11-02:

> **这两个语料不在本仓库里。** 仓库只随附 `examples/` 的 4 个上游 workflow，实测
> `python3 -m matrix_reach.cli examples/` 输出是
> `files=4 matrices=13 skipped=1 combinations=68 errors=0 notes=39`。
> 下表的 188/43 来自**外部语料**：`actions/starter-workflows` 的全部 `.yml`，加上
> pandas / django / CPython 三个仓库的 `.github/workflows/*.yml`；本仓库目前**没有随附
> 取语料的脚本**，所以这两个数字不能在本仓库内一条命令复现，只能当作"外部非随附测量"。
> 要抬回可复现，下一步应提交抓取脚本 + 语料清单哈希。

| corpus | files | matrices | skipped (expressions) | combinations | errors | notes |
|---|---|---|---|---|---|---|
| `actions/starter-workflows` (all `.yml`) | 129 | 15 | 1 | 37 | **0** | 2 |
| pandas + django + cpython workflows | 59 | 28 | 2 | 160 | **0** | 40 |
| total | **188** | **43** | **3** | **197** | **0** | **42** |

The two starter-workflow notes are `max-parallel: 4` on a 3-combination Django matrix
(redundant, harmless). The 40 real-repo notes are intentional extra combinations in
pandas and CPython; none is a contradiction. **The honest result is zero errors in 188
curated workflows** — the audit is useful because it says so instead of inventing
defects to look busy.

## Why a mutation proof

Every rule ships with a tiny workflow that contains exactly the defect the rule claims
to catch. `--self-test` runs all ten; if any rule stops firing, the command exits **2**
and refuses to give a verdict. This is the difference between "we have a linter" and
"we know the linter still works".

## Reproduce

```bash
python3 -m pip install -e .
python3 -m unittest discover -s tests -v    # 11 tests
python3 -m matrix_reach.cli --self-test
python3 -m matrix_reach.cli examples/
```

`examples/` contains four verbatim upstream workflows (MIT/Apache-2.0) used as
fixtures: cmake-multi-platform, Django, pandas unit-tests, CPython build.

## Limits

- Matrix values must be literal; expressions skip the job.
- `include`/`exclude` semantics are implemented from GitHub's documented rule, not
  verified against a live Actions run.
- The parser is PyYAML; YAML anchors/merge keys are resolved before the audit.
- No check that the job actually uses every matrix key (dead axes are legal).

## License

MIT.
