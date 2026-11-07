"""Tests for the saved-flow TaskCall migration: inventory, conversion, and safety."""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

from qdash.common.migration.task_calls import WriteConflictError, analyze_source, main, run

LEGACY_FLOW = textwrap.dedent(
    '''
    """A saved flow from before task calls."""

    from qdash.workflow.service import CalibService
    from qdash.workflow.service.steps import CustomOneQubit, OneQubitCheck

    CHECK_TASKS: list[str] = [
        "Configure",  # apply the configuration first
        "CheckRabi",
        "CheckRabi",  # measure again at the new amplitude
    ]


    def my_flow(username, chip_id, tasks: list[str] | None = None):
        cal = CalibService(username, chip_id, task_run_parameters={"CheckT1": {"shots": 1}})
        steps = [
            OneQubitCheck(tasks=CHECK_TASKS),
            CustomOneQubit(
                step_name="coherence",
                tasks=["Configure", "CheckT1", "CheckT2Echo"],
                continue_on_failure=True,
                stop_on_failure_tasks=("Configure",),
            ),
            CustomOneQubit(step_name="chosen", tasks=tasks),
            CustomOneQubit(step_name="built", tasks=[name for name in ["CheckT1"]]),
            CustomOneQubit(step_name="ramsey", tasks=["CheckRamsey"], task_parameters={}),
        ]
        return cal.run(None, steps=steps)
    '''
)


def _kinds(report: object) -> list[tuple[str, bool]]:
    return [(finding.kind, finding.converted) for finding in report.findings]  # type: ignore[attr-defined]


def test_literal_lists_are_converted_and_the_rest_reported() -> None:
    report = analyze_source(LEGACY_FLOW, "flow.py")

    assert report.error is None
    assert sorted(_kinds(report)) == sorted(
        [
            ("task_names", True),  # CHECK_TASKS
            ("task_names", True),  # coherence literal
            ("stop_on_failure_tasks", True),
            ("task_run_parameters", False),
            ("task_name_parameter", False),
            ("dynamic_tasks", False),
            ("task_names", True),  # ramsey literal
            ("step_task_parameters", False),
        ]
    )
    converted = report.converted_source
    assert converted is not None
    ast.parse(converted)
    assert "from qdash.workflow import TaskCall" in converted
    assert "CHECK_TASKS: list[TaskCall] = [" in converted
    # Repeated names get explicit call ids; comments stay where they were.
    assert 'TaskCall(name="CheckRabi", call_id="CheckRabi"),' in converted
    assert (
        'TaskCall(name="CheckRabi", call_id="CheckRabi_2"),  # measure again at the new amplitude'
        in converted
    )
    assert 'TaskCall(name="Configure"),  # apply the configuration first' in converted
    # The prerequisite keeps failing fast through its own call policy.
    assert 'TaskCall(name="Configure", on_failure="stop")' in converted
    assert "stop_on_failure_tasks" not in converted
    assert "continue_on_failure=True," in converted


def test_converted_flow_builds_valid_steps() -> None:
    report = analyze_source(LEGACY_FLOW, "flow.py")
    assert report.converted_source is not None
    tree = ast.parse(report.converted_source)
    check_tasks = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "CHECK_TASKS"
    )
    from qdash.datamodel.task_call import TaskCall, normalize_calls

    calls = eval(  # noqa: S307 - evaluating the converted literal only, in the test
        compile(ast.Expression(check_tasks.value), "<converted>", "eval"),  # type: ignore[arg-type]
        {"TaskCall": TaskCall},
    )
    assert [call.resolved_call_id for call in normalize_calls(calls)] == [
        "Configure",
        "CheckRabi",
        "CheckRabi_2",
    ]


def test_a_shared_list_with_different_stop_policies_is_left_for_a_person() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow.service.steps import CustomOneQubit

        TASKS = ["Configure", "CheckT1"]
        steps = [
            CustomOneQubit(step_name="a", tasks=TASKS, stop_on_failure_tasks=("Configure",)),
            CustomOneQubit(step_name="b", tasks=TASKS),
        ]
        """
    )
    report = analyze_source(source)
    assert ("shared_list", False) in _kinds(report)


def test_converted_flows_need_no_attention() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow import TaskCall
        from qdash.workflow.service.steps import CustomOneQubit
        from qdash.workflow.service.tasks import CHECK_1Q_TASKS

        steps = [
            CustomOneQubit(step_name="a", tasks=[TaskCall(name="CheckT1")]),
            CustomOneQubit(step_name="b", tasks=CHECK_1Q_TASKS),
        ]
        """
    )
    report = analyze_source(source)
    assert report.findings == []
    assert report.converted_source is None
    assert not report.needs_attention


def test_unparseable_files_are_reported_not_raised() -> None:
    report = analyze_source("def broken(:\n", "broken.py")
    assert report.error is not None
    assert report.needs_attention


def test_run_writes_converted_copies_only_to_another_directory(tmp_path: Path) -> None:
    flows = tmp_path / "user_flows" / "alice"
    flows.mkdir(parents=True)
    original = flows / "legacy.py"
    original.write_text(LEGACY_FLOW, encoding="utf-8")
    (flows / "current.py").write_text("x = 1\n", encoding="utf-8")
    out = tmp_path / "converted"

    reports = run([tmp_path / "user_flows"], out)

    assert {Path(report.path).name for report in reports} == {"legacy.py", "current.py"}
    assert original.read_text(encoding="utf-8") == LEGACY_FLOW
    converted = out / "alice" / "legacy.py"
    assert "TaskCall" in converted.read_text(encoding="utf-8")
    assert not (out / "alice" / "current.py").exists()
    with pytest.raises(WriteConflictError, match="would overwrite"):
        run([flows], flows)


def test_cli_exit_status_reflects_what_needs_attention(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy = tmp_path / "legacy.py"
    legacy.write_text(LEGACY_FLOW, encoding="utf-8")
    current = tmp_path / "current.py"
    current.write_text("x = 1\n", encoding="utf-8")

    assert main([str(current)]) == 0
    assert main([str(legacy)]) == 1
    output = capsys.readouterr().out
    assert "[converted]" in output and "[manual]" in output
    assert main([str(legacy), "--json"]) == 1


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("call result", "names = build_tasks()\nCustomOneQubit(tasks=names)\n"),
        ("never assigned", "CustomOneQubit(tasks=names)\n"),
        ("user module import", "from mylib import TASKS\nCustomOneQubit(tasks=TASKS)\n"),
        ("unannotated parameter", "def f(tasks=None):\n    return CustomOneQubit(tasks=tasks)\n"),
        ("comprehension of names", "CustomOneQubit(tasks=[n for n in ['CheckT1']])\n"),
        (
            "reassigned list",
            "NAMES = ['CheckT1']\nNAMES = NAMES + ['CheckT2Echo']\nCustomOneQubit(tasks=NAMES)\n",
        ),
        (
            "rebound through global",
            "NAMES = ['CheckT1']\ndef load():\n    global NAMES\n    NAMES = read()\n"
            "CustomOneQubit(tasks=NAMES)\n",
        ),
        (
            "loop target",
            "for names in groups:\n    CustomOneQubit(tasks=names)\n",
        ),
        (
            "class attribute is not visible in a method",
            "class Flow:\n    T = ['CheckT1']\n    def step(self):\n"
            "        return CustomOneQubit(tasks=T)\n",
        ),
        (
            "TaskCall list extended with names",
            "from qdash.workflow import TaskCall\nC = [TaskCall(name='CheckT1')]\n"
            "C.extend(['CheckRabi'])\nCustomOneQubit(tasks=C)\n",
        ),
        ("positional arguments", "CustomOneQubit('check')\n"),
    ],
)
def test_task_lists_the_check_cannot_prove_are_reported_for_a_person(
    label: str, source: str
) -> None:
    report = analyze_source(source)
    assert "dynamic_tasks" in [finding.kind for finding in report.manual], label
    assert report.needs_attention
    assert report.converted_source is None


def test_a_local_variable_shadowing_a_module_list_is_judged_by_its_own_value() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow.service.steps import CustomOneQubit

        NAMES = ["CheckT1"]


        def flow():
            NAMES = build()
            return CustomOneQubit(step_name="local", tasks=NAMES)


        top = CustomOneQubit(step_name="top", tasks=NAMES)
        """
    )
    report = analyze_source(source)

    assert sorted(_kinds(report)) == [("dynamic_tasks", False), ("task_names", True)]
    dynamic = next(finding for finding in report.findings if finding.kind == "dynamic_tasks")
    assert dynamic.line == 9  # the step inside flow(), whose NAMES is build()
    assert report.converted_source is not None
    assert 'NAMES = [TaskCall(name="CheckT1")]' in report.converted_source
    assert "NAMES = build()" in report.converted_source


def test_a_local_name_list_is_converted_in_its_own_scope() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow.service.steps import CustomOneQubit

        NAMES = make()


        def flow():
            NAMES = ["CheckRamsey", "CheckRamsey"]
            return CustomOneQubit(tasks=NAMES)
        """
    )
    report = analyze_source(source)

    assert _kinds(report) == [("task_names", True)]
    assert report.converted_source is not None
    assert "NAMES = make()" in report.converted_source
    assert 'TaskCall(name="CheckRamsey", call_id="CheckRamsey_2")' in report.converted_source


def test_a_name_list_used_outside_tasks_is_not_rewritten() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow.service.steps import CustomOneQubit

        NAMES = ["CheckT1", "CheckRabi"]
        NAMES.append("CheckT2Echo")
        LABEL = ",".join(NAMES)
        CustomOneQubit(tasks=NAMES, stop_on_failure_tasks=("CheckT1",))
        """
    )
    report = analyze_source(source)

    assert sorted(_kinds(report)) == [("shared_list", False), ("stop_on_failure_tasks", False)]
    assert report.converted_source is None


def test_a_shared_list_with_different_stop_policies_is_not_rewritten_for_either_step() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow.service.steps import CustomOneQubit

        TASKS = ["Configure", "CheckT1"]
        a = CustomOneQubit(step_name="b", tasks=TASKS)
        b = CustomOneQubit(step_name="a", tasks=TASKS, stop_on_failure_tasks=("Configure",))
        """
    )
    report = analyze_source(source)

    assert all(not finding.converted for finding in report.findings)
    # Converting the list for one step would silently change the other step's policy.
    assert report.converted_source is None


def test_a_list_shared_with_the_same_stop_policy_is_converted_once() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow.service.steps import CustomOneQubit

        TASKS = ["Configure", "CheckT1"]
        a = CustomOneQubit(step_name="a", tasks=TASKS, stop_on_failure_tasks=("Configure",))
        b = CustomOneQubit(step_name="b", tasks=TASKS, stop_on_failure_tasks=("Configure",))
        """
    )
    report = analyze_source(source)

    assert report.manual == []
    assert report.converted_source is not None
    assert report.converted_source.count('on_failure="stop"') == 1
    assert "stop_on_failure_tasks" not in report.converted_source


@pytest.mark.parametrize(
    "source",
    [
        # A flow parameter with a TaskCall default filled in by the body, as in the templates.
        """
        from qdash.workflow import TaskCall
        from qdash.workflow.service.steps import CustomOneQubit

        DEFAULT: list[TaskCall] = [TaskCall(name="CheckRabi")]


        def flow(tasks: list[TaskCall] | None = None):
            if tasks is None:
                tasks = list(DEFAULT)
            tasks += [TaskCall(name="CheckT1")]
            tasks.append(TaskCall(name="CheckT1", call_id="t1_again"))
            return CustomOneQubit(tasks=tasks)
        """,
        """
        from qdash.workflow import TaskCall
        from qdash.workflow.service.steps import CustomOneQubit

        names = ["CheckT1"]
        step = CustomOneQubit(tasks=[TaskCall(name=n) for n in names])
        none = CustomOneQubit(tasks=None)
        """,
    ],
)
def test_task_call_lists_the_check_can_follow_need_no_attention(source: str) -> None:
    report = analyze_source(textwrap.dedent(source))
    assert report.findings == []
    assert report.converted_source is None


def test_a_name_list_parameter_is_reported_only_where_it_reaches_a_step() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow import TaskCall
        from qdash.workflow.service.steps import CustomOneQubit

        CALLS = [TaskCall(name="CheckT1")]


        def helper(names: list[str]):
            return names


        def flow(names: list[str]):
            return CustomOneQubit(tasks=CALLS)
        """
    )
    assert analyze_source(source).findings == []


def test_templates_need_no_migration() -> None:
    templates = Path(__file__).parents[3] / "src" / "qdash" / "workflow" / "templates"
    reports = run(sorted(templates.glob("*.py")), None)
    assert reports
    assert [report.path for report in reports if report.needs_attention] == []


def test_the_task_call_import_is_added_when_only_a_function_imports_it() -> None:
    source = textwrap.dedent(
        """
        from qdash.workflow.service.steps import CustomOneQubit

        NAMES = ["CheckT1"]


        def flow():
            from qdash.workflow import TaskCall

            return CustomOneQubit(tasks=NAMES)
        """
    )
    converted = analyze_source(source).converted_source
    assert converted is not None
    module_imports = [
        node for node in ast.parse(converted).body if isinstance(node, ast.ImportFrom)
    ]
    assert any(alias.name == "TaskCall" for node in module_imports for alias in node.names)


# ------------------------------------------------------------------ write safety


def test_run_refuses_a_destination_that_is_another_input(tmp_path: Path) -> None:
    # Converting a/flow.py into b/ would replace b's own original before b is read.
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / "flow.py").write_text(LEGACY_FLOW, encoding="utf-8")
    second_source = LEGACY_FLOW.replace("coherence", "other")
    (second / "flow.py").write_text(second_source, encoding="utf-8")

    with pytest.raises(WriteConflictError, match="would overwrite the input") as error:
        run([first, second], second)

    assert "nothing was written" in str(error.value)
    assert (first / "flow.py").read_text(encoding="utf-8") == LEGACY_FLOW
    assert (second / "flow.py").read_text(encoding="utf-8") == second_source
    assert sorted(path.name for path in second.iterdir()) == ["flow.py"]


def test_run_refuses_a_destination_reached_through_a_symlink(tmp_path: Path) -> None:
    flows = tmp_path / "flows"
    flows.mkdir()
    (flows / "flow.py").write_text(LEGACY_FLOW, encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(flows, target_is_directory=True)

    with pytest.raises(WriteConflictError, match="would overwrite the input"):
        run([flows], alias)
    assert (flows / "flow.py").read_text(encoding="utf-8") == LEGACY_FLOW


def test_run_refuses_two_inputs_with_one_destination_and_writes_nothing(tmp_path: Path) -> None:
    for root in ("a", "b"):
        (tmp_path / root).mkdir()
        (tmp_path / root / "flow.py").write_text(LEGACY_FLOW, encoding="utf-8")
    (tmp_path / "a" / "only_a.py").write_text(LEGACY_FLOW, encoding="utf-8")
    out = tmp_path / "out"

    with pytest.raises(WriteConflictError, match="would both be written to"):
        run([tmp_path / "a", tmp_path / "b"], out)
    assert not out.exists()


def test_run_does_not_clobber_an_unrelated_file(tmp_path: Path) -> None:
    flows = tmp_path / "flows"
    flows.mkdir()
    (flows / "flow.py").write_text(LEGACY_FLOW, encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    unrelated = out / "flow.py"
    unrelated.write_text("keep me\n", encoding="utf-8")

    with pytest.raises(WriteConflictError, match="would overwrite an existing file"):
        run([flows], out)
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"

    # Re-running into a directory that already holds the same conversion is fine.
    unrelated.unlink()
    run([flows], out)
    first = unrelated.read_text(encoding="utf-8")
    run([flows], out)
    assert unrelated.read_text(encoding="utf-8") == first


def test_cli_reports_a_write_conflict_with_status_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flows = tmp_path / "flows"
    flows.mkdir()
    (flows / "flow.py").write_text(LEGACY_FLOW, encoding="utf-8")
    assert main([str(flows), "--write-to", str(flows)]) == 2
    assert "nothing was written" in capsys.readouterr().err
    assert (flows / "flow.py").read_text(encoding="utf-8") == LEGACY_FLOW


def test_run_reports_undecodable_files_and_continues(tmp_path: Path) -> None:
    (tmp_path / "binary.py").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "legacy.py").write_text(LEGACY_FLOW, encoding="utf-8")
    reports = {Path(report.path).name: report for report in run([tmp_path], None)}
    assert reports["binary.py"].error is not None
    assert reports["legacy.py"].converted_source is not None


# --------------------------------------------------------------- source handling


def _converted(source: str) -> str:
    report = analyze_source(source)
    assert report.error is None
    assert report.converted_source is not None, report.findings
    ast.parse(report.converted_source)
    return report.converted_source


def _first_line(source: str, text: str) -> int:
    return next(index for index, line in enumerate(source.splitlines()) if text in line)


def test_the_import_precedes_the_first_use() -> None:
    converted = _converted('NAMES = ["CheckT1"]\nimport os\nCustomOneQubit(tasks=NAMES)\n')
    assert _first_line(converted, "import TaskCall") < _first_line(converted, "TaskCall(name=")


def test_the_import_follows_the_docstring_and_future_imports() -> None:
    converted = _converted(
        '"""Flow."""\nfrom __future__ import annotations\n\nCustomOneQubit(tasks=["CheckT1"])'
    )
    assert converted.startswith(
        '"""Flow."""\nfrom __future__ import annotations\nfrom qdash.workflow import TaskCall\n'
    )


def test_an_expression_first_statement_is_not_a_docstring() -> None:
    converted = _converted('CustomOneQubit(tasks=["CheckT1"])')
    assert converted == (
        'from qdash.workflow import TaskCall\nCustomOneQubit(tasks=[TaskCall(name="CheckT1")])'
    )


def test_the_import_keeps_a_shebang_and_encoding_line_first() -> None:
    converted = _converted(
        '#!/usr/bin/env python\n# -*- coding: utf-8 -*-\nX = ["CheckT1"]\nCustomOneQubit(tasks=X)\n'
    )
    assert converted.splitlines()[:3] == [
        "#!/usr/bin/env python",
        "# -*- coding: utf-8 -*-",
        "from qdash.workflow import TaskCall",
    ]


def test_a_decorated_use_gets_the_import_before_the_decorator() -> None:
    converted = _converted(
        'import os\n\n@register(CustomOneQubit(tasks=["CheckT1"]))\ndef flow():\n    pass\n'
    )
    assert _first_line(converted, "import TaskCall") < _first_line(converted, "@register")


def test_a_taskcall_from_another_module_is_left_for_a_person() -> None:
    report = analyze_source('from mylib import TaskCall\nCustomOneQubit(tasks=["CheckT1"])\n')
    assert report.converted_source is None
    assert ("conversion_failed", False) in _kinds(report)
    assert all(not finding.converted for finding in report.findings)


@pytest.mark.parametrize("separator", ["\n", "; "])
def test_a_late_taskcall_import_is_left_for_a_person(separator: str) -> None:
    source = (
        "from qdash.workflow import CustomOneQubit\n"
        'step = CustomOneQubit(tasks=["CheckT1"])'
        + separator
        + "from qdash.workflow import TaskCall\n"
    )
    report = analyze_source(source)
    assert report.converted_source is None
    assert ("conversion_failed", False) in _kinds(report)
    assert all(not finding.converted for finding in report.findings)
    assert any("must precede" in finding.message for finding in report.findings)


def test_an_early_taskcall_import_is_reused() -> None:
    converted = _converted(
        'from qdash.workflow import TaskCall\nCustomOneQubit(tasks=["CheckT1"])\n'
    )
    assert converted.count("import TaskCall") == 1
    assert _first_line(converted, "import TaskCall") < _first_line(converted, "TaskCall(name=")


@pytest.mark.parametrize(
    ("names", "ids"),
    [
        (["X", "X", "X_2"], ["X", "X_3", "X_2"]),
        (["X_2", "X", "X"], ["X_2", "X", "X_3"]),
        (["X", "X", "X"], ["X", "X_2", "X_3"]),
    ],
)
def test_generated_call_ids_are_unique(names: list[str], ids: list[str]) -> None:
    from qdash.datamodel.task_call import TaskCall, normalize_calls

    literal = ", ".join(f'"{name}"' for name in names)
    converted = _converted(f"CustomOneQubit(tasks=[{literal}])\n")
    call = ast.parse(converted).body[-1].value  # type: ignore[attr-defined]
    calls = eval(  # noqa: S307 - evaluating the converted literal only, in the test
        compile(ast.Expression(call.keywords[0].value), "<converted>", "eval"),
        {"TaskCall": TaskCall},
    )
    assert [c.resolved_call_id for c in normalize_calls(calls)] == ids


def test_long_repeated_names_get_call_ids_within_the_limit() -> None:
    from qdash.datamodel.task_call import CALL_ID_PATTERN

    name = "C" + "x" * 80
    converted = _converted(f'CustomOneQubit(tasks=["{name}", "{name}"])\n')
    ids = re.findall(r'call_id="([^"]+)"', converted)
    assert len(set(ids)) == 2
    assert all(re.fullmatch(CALL_ID_PATTERN, call_id) for call_id in ids)


@pytest.mark.parametrize(
    "header",
    ["# comment\ftext\n", "# a\u2028b\n", "# a\x1cb\n", "# caf\u00e9\n"],
)
def test_line_separators_python_does_not_split_on(header: str) -> None:
    converted = _converted(header + 'CustomOneQubit(step_name="\u00e9", tasks=["X", "X"])\n')
    assert header in converted
    assert 'TaskCall(name="X", call_id="X_2")' in converted


def test_crlf_line_endings_are_kept() -> None:
    source = (
        "from qdash.workflow.service.steps import CustomOneQubit\r\n"
        'CustomOneQubit(\r\n    tasks=["X"],\r\n    stop_on_failure_tasks=["X"],\r\n)\r\n'
    )
    converted = _converted(source)
    assert "\n" not in converted.replace("\r\n", "")
    assert "stop_on_failure_tasks" not in converted
    assert "from qdash.workflow import TaskCall\r\n" in converted


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            'CustomOneQubit(\n stop_on_failure_tasks=["X"]\n , tasks=["X"]\n)\n',
            'CustomOneQubit(\n tasks=[TaskCall(name="X", on_failure="stop")]\n)\n',
        ),
        (
            'CustomOneQubit(tasks=["X"], stop_on_failure_tasks=(["X"]))\n',
            'CustomOneQubit(tasks=[TaskCall(name="X", on_failure="stop")])\n',
        ),
        (
            'CustomOneQubit(\n    tasks=["X"],\n    stop_on_failure_tasks=("X",),  # why\n'
            "    continue_on_failure=True,\n)\n",
            'CustomOneQubit(\n    tasks=[TaskCall(name="X", on_failure="stop")],\n    # why\n'
            "    continue_on_failure=True,\n)\n",
        ),
        (
            'CustomOneQubit(\n    tasks=["X"],\n    stop_on_failure_tasks=("X",)\n)\n',
            'CustomOneQubit(\n    tasks=[TaskCall(name="X", on_failure="stop")]\n)\n',
        ),
        (
            'CustomOneQubit(stop_on_failure_tasks=["X"], tasks=["X"])\n',
            'CustomOneQubit(tasks=[TaskCall(name="X", on_failure="stop")])\n',
        ),
    ],
)
def test_stop_on_failure_tasks_removal_keeps_valid_syntax(source: str, expected: str) -> None:
    converted = _converted(source)
    assert converted == "from qdash.workflow import TaskCall\n" + expected


def test_a_conversion_failure_is_reported_per_file(tmp_path: Path) -> None:
    (tmp_path / "foreign.py").write_text(
        'from mylib import TaskCall\nCustomOneQubit(tasks=["X"])\n', encoding="utf-8"
    )
    (tmp_path / "legacy.py").write_text(LEGACY_FLOW, encoding="utf-8")
    out = tmp_path / "out"
    reports = {Path(report.path).name: report for report in run([tmp_path], out)}
    assert reports["foreign.py"].converted_source is None
    assert not (out / "foreign.py").exists()
    assert (out / "legacy.py").exists()


def test_null_bytes_are_a_parse_error_not_a_crash() -> None:
    report = analyze_source("x = 1\x00\n")
    assert report.error is not None
