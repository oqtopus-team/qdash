"""Fake QOP device of the ``qm-fake`` backend.

``QMFakeQuantumMachinesManager`` stands in for ``qm.QuantumMachinesManager`` at the
device execution boundary. It implements the narrow part of the SDK API that the
qualang-tools Rabi experiment and QDash's result fetcher use:

* ``manager.open_qm(config)`` validates ``config`` offline with the SDK's own
  ``qm.program.load_config`` and returns a quantum machine;
* ``machine.execute(program)`` takes the ``qm.Program`` the real library generated,
  decodes its protobuf (``program.qua_program``), interprets it and returns a job;
* ``job.result_handles`` offers ``wait_for_all_values()`` and ``get(name).fetch_all()``
  with the stream names and shapes that the program's stream processing declares;
* ``machine.close()`` and ``manager.close()`` end the lifecycle.

Supported QUA subset. The interpreter accepts exactly what a 1D amplitude Rabi needs
and fails closed with ``QMFakeUnsupportedError`` on anything else, including any
protobuf field it does not know (schema drift of a newer SDK):

* scalar ``int``/``fixed``/``bool`` variables (no arrays, input or external streams);
* ``for_`` loops whose init and update assign the loop variable, with literals,
  variables, ``+ - *`` and comparisons in expressions;
* ``play(op * amp(a), element)`` with a scalar amplitude and no duration, condition,
  chirp, truncate or target input, on the drive element of a configured qubit;
* ``measure(op, element, None, demod.full(...)/dual_demod.full(...))`` into scalar
  variables, on the readout element of a configured qubit;
* ``align``, ``wait`` (timing is not modelled), ``save`` to a stream;
* stream processing ``save(name, ...)`` over ``average()``, ``buffer(n)`` and raw
  streams.

Model. Each qubit starts in the ground state. A ``play`` rotates it by
``pi * a * |area| / pi_pulse_area``, where ``area`` is the summed complex envelope of
the pulse's configured waveforms in V*ns. A ``measure`` projects it, with excited
probability ``sin(theta / 2) ** 2``, onto the ground or excited readout amplitude
``s`` (V), adds Gaussian noise of ``noise_per_shot`` per quadrature and resets the
qubit, standing in for the cooldown. Demodulation is cycle-averaged: the first
configured output carries ``Re(s exp(i w t))`` and the second ``Im(s exp(i w t))``, so
an integration weight with cosine sum ``C`` and sine sum ``S`` (V*ns of weight) gives
``2**-12 * (C Re z - S Im z) / 2`` with ``z = s`` on the first output and
``z = -i s`` on the second, stored as a QUA ``fixed`` value. With unit weights over
the readout length, dual demodulation therefore returns ``Re s`` and ``Im s`` after
``demod2volts``. No QUA compilation, controller timing, IF ripple, time of flight,
smearing, ADC quantisation, decoherence or wiring is modelled or checked.
"""

from __future__ import annotations

import itertools
import math
import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qm_fake import QMFakeSettings

# QUA ``fixed`` is a signed 4.28 fixed-point number.
FIXED_FRACTION_BITS = 28
FIXED_SCALE = float(1 << FIXED_FRACTION_BITS)
FIXED_MIN = -8.0
FIXED_MAX = 8.0
INT_MIN = -(2**31)
INT_MAX = 2**31 - 1
# QUA ``amp()`` scales accept values in [-2, 2).
AMP_MIN = -2.0
AMP_MAX = 2.0
# Demodulation results are sums of 12-bit-scaled products (see ``unit.demod2volts``).
DEMOD_SCALE = 2.0**-12
# Bound on interpreted statements, so a malformed loop cannot run forever.
MAX_EXECUTED_STATEMENTS = 20_000_000
# Arbitrary waveforms are supported at the default 1 GS/s only.
DEFAULT_SAMPLING_RATE = 1e9
# Protobuf fields that carry source locations only.
IGNORED_FIELDS = frozenset({"loc"})


class QMFakeUnsupportedError(RuntimeError):
    """Raised when a program or configuration is outside what the fake device supports."""


def _quantize_fixed(value: float) -> float:
    if not FIXED_MIN <= value < FIXED_MAX:
        raise QMFakeUnsupportedError(f"fixed value {value} overflows the QUA range [-8, 8)")
    return round(value * FIXED_SCALE) / FIXED_SCALE


def _check_int(value: int) -> int:
    if not INT_MIN <= value <= INT_MAX:
        raise QMFakeUnsupportedError(f"int value {value} overflows a 32-bit QUA int")
    return value


def _set_fields(message: Any) -> set[str]:
    return {descriptor.name for descriptor, _ in message.ListFields()} - IGNORED_FIELDS


def _require_fields(message: Any, allowed: set[str], what: str) -> None:
    """Fail closed when ``message`` sets a field the fake device does not interpret."""
    unknown = _set_fields(message) - allowed
    if unknown:
        raise QMFakeUnsupportedError(
            f"{what} uses {', '.join(sorted(unknown))}, which the qm-fake device does not support"
        )


# ---------------------------------------------------------------------------
# Configuration view
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DemodWeight:
    cosine: float
    sine: float


class _ConfigView:
    """Read-only access to the protobuf configuration produced by ``load_config``."""

    def __init__(self, pb_config: Any) -> None:
        version = pb_config.WhichOneof("config_version")
        if version != "v1beta":
            raise QMFakeUnsupportedError(f"QUA configuration version {version} is not supported")
        self._config = pb_config.v1beta

    def has_element(self, name: str) -> bool:
        return name in self._config.elements

    def element(self, name: str) -> Any:
        if name not in self._config.elements:
            raise QMFakeUnsupportedError(f"element '{name}' is not in the QUA configuration")
        return self._config.elements[name]

    def pulse(self, element: str, operation: str) -> Any:
        operations = self.element(element).operations
        if operation not in operations:
            raise QMFakeUnsupportedError(f"operation '{operation}' is not defined for '{element}'")
        return self._config.pulses[operations[operation]]

    def envelope_area(self, element: str, operation: str) -> float:
        """Magnitude of the summed complex envelope of a control pulse, in V*ns."""
        pulse = self.pulse(element, operation)
        length = int(pulse.length)
        area = 0j
        for port, waveform_name in pulse.waveforms.items():
            if port not in ("I", "Q", "single"):
                raise QMFakeUnsupportedError(f"waveform input '{port}' is not supported")
            total = self._waveform_sum(waveform_name, length)
            area += 1j * total if port == "Q" else total
        return abs(area)

    def _waveform_sum(self, name: str, length: int) -> float:
        waveform = self._config.waveforms[name]
        kind = waveform.WhichOneof("waveform_oneof")
        if kind == "constant":
            return float(waveform.constant.sample) * length
        if kind == "arbitrary":
            arbitrary = waveform.arbitrary
            rate = float(arbitrary.samplingRate.value) if arbitrary.HasField("samplingRate") else 0
            if rate not in (0.0, DEFAULT_SAMPLING_RATE):
                raise QMFakeUnsupportedError(
                    f"waveform '{name}' uses a sampling rate of {rate} Hz; only 1 GS/s is supported"
                )
            if len(arbitrary.samples) != length:
                raise QMFakeUnsupportedError(
                    f"waveform '{name}' has {len(arbitrary.samples)} samples for a {length} ns pulse"
                )
            return float(sum(arbitrary.samples))
        raise QMFakeUnsupportedError(f"waveform '{name}' of type {kind} is not supported")

    def demod_weight(self, element: str, operation: str, weight_name: str) -> _DemodWeight:
        """Cosine and sine sums of an integration weight of a measurement pulse, in ns."""
        pulse = self.pulse(element, operation)
        if weight_name not in pulse.integrationWeights:
            raise QMFakeUnsupportedError(
                f"integration weight '{weight_name}' is not defined for operation '{operation}'"
            )
        weight = self._config.integrationWeights[pulse.integrationWeights[weight_name]]
        sums = []
        for segments in (weight.cosine, weight.sine):
            covered = sum(int(segment.length) for segment in segments)
            if covered != int(pulse.length):
                raise QMFakeUnsupportedError(
                    f"integration weight '{weight_name}' covers {covered} ns of a "
                    f"{int(pulse.length)} ns readout pulse"
                )
            sums.append(sum(float(segment.value) * int(segment.length) for segment in segments))
        return _DemodWeight(cosine=sums[0], sine=sums[1])


# ---------------------------------------------------------------------------
# Program interpreter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MeasuredValue:
    """Placeholder for a demodulated value, resolved once all measurements are drawn."""

    measurement: int
    re_coefficient: float
    im_coefficient: float


Value = int | float | bool | _MeasuredValue
Env = dict[str, Value]
Expr = Callable[[Env], int | float | bool]


@dataclass
class _QubitBinding:
    qid: str
    drive_element: str
    readout_element: str
    outputs: tuple[str, ...]
    pi_pulse_area: float


@dataclass
class _ExecutionState:
    env: Env
    rotation: dict[str, float]
    probabilities: list[float] = field(default_factory=list)
    measured_qids: list[str] = field(default_factory=list)
    streams: dict[str, list[Value]] = field(default_factory=dict)
    played_amplitudes: dict[str, list[float]] = field(default_factory=dict)
    executed: int = 0

    def tick(self) -> None:
        self.executed += 1
        if self.executed > MAX_EXECUTED_STATEMENTS:
            raise QMFakeUnsupportedError(
                f"the program executes more than {MAX_EXECUTED_STATEMENTS} statements"
            )


Statement = Callable[[_ExecutionState], None]

_COMPARISONS: dict[str, Callable[[Any, Any], bool]] = {
    "LT": operator.lt,
    "LET": operator.le,
    "GT": operator.gt,
    "GET": operator.ge,
    "EQ": operator.eq,
}
_ARITHMETIC: dict[str, Callable[[Any, Any], Any]] = {
    "ADD": operator.add,
    "SUB": operator.sub,
    "MULT": operator.mul,
}


class _ProgramCompiler:
    """Translate a ``QuaProgram`` protobuf into Python closures, validating every node."""

    def __init__(
        self, qua_program: Any, config: _ConfigView, bindings: dict[str, _QubitBinding]
    ) -> None:
        self._program = qua_program
        self._config = config
        self._by_drive = {b.drive_element: b for b in bindings.values()}
        self._by_readout = {b.readout_element: b for b in bindings.values()}
        self._types: dict[str, str] = {}
        self.initial_env: Env = {}
        self.saved_tags: set[str] = set()
        self._binary_op_names = self._enum_names("BinaryExpression", "op")
        self._type_names = self._enum_names("LiteralExpression", "type")

    def _enum_names(self, message: str, field_name: str) -> dict[int, str]:
        descriptor = self._program.DESCRIPTOR.nested_types_by_name[message]
        enum = descriptor.fields_by_name[field_name].enum_type
        return {value.number: value.name for value in enum.values}

    def compile(self) -> list[Statement]:
        _require_fields(self._program, {"script", "resultAnalysis"}, "the QUA program")
        script = self._program.script
        _require_fields(script, {"variables", "body"}, "the QUA script")
        for declaration in script.variables:
            self._declare(declaration)
        return self._block(script.body)

    def _declare(self, declaration: Any) -> None:
        if declaration.size != 1:
            raise QMFakeUnsupportedError(f"QUA array '{declaration.name}' is not supported")
        _require_fields(declaration, {"name", "type", "size", "value"}, "a variable declaration")
        kind = self._type_names[declaration.type]
        initial: Value
        if declaration.value:
            (literal,) = declaration.value
            initial = self._literal_value(literal, kind)
        else:
            initial = {"INT": 0, "REAL": 0.0, "BOOL": False}[kind]
        self._types[declaration.name] = kind
        self.initial_env[declaration.name] = initial

    def _literal_value(self, literal: Any, kind: str) -> int | float | bool:
        text = str(literal.value)
        if kind == "INT":
            return _check_int(int(text))
        if kind == "REAL":
            return _quantize_fixed(float(text))
        if text not in ("true", "false", "True", "False"):
            raise QMFakeUnsupportedError(f"boolean literal {text!r} is not supported")
        return text.lower() == "true"

    def _block(self, collection: Any) -> list[Statement]:
        _require_fields(collection, {"statements"}, "a statement block")
        return [self._statement(statement) for statement in collection.statements]

    def _statement(self, statement: Any) -> Statement:
        kind = statement.WhichOneof("statement_oneof")
        handler = {
            "for": self._for,
            "play": self._play,
            "measure": self._measure,
            "align": self._align,
            "wait": self._wait,
            "save": self._save,
        }.get(kind or "")
        if handler is None:
            raise QMFakeUnsupportedError(
                f"QUA statement '{kind}' is not supported by the qm-fake device, which runs the "
                "1D amplitude Rabi subset only"
            )
        return handler(getattr(statement, kind))

    # -- statements -----------------------------------------------------------------

    def _loop_assignment(self, collection: Any, what: str) -> tuple[str, Expr]:
        statements = list(collection.statements)
        if len(statements) != 1 or statements[0].WhichOneof("statement_oneof") != "assign":
            raise QMFakeUnsupportedError(f"a for_ {what} must be a single assignment")
        assign = statements[0].assign
        _require_fields(assign, {"target", "expression"}, "a for_ assignment")
        target = assign.target
        if target.WhichOneof("target") != "variable":
            raise QMFakeUnsupportedError("a for_ loop must assign a scalar variable")
        _require_fields(target.variable, {"name"}, "a for_ loop variable")
        return target.variable.name, self._expression(assign.expression)

    def _for(self, loop: Any) -> Statement:
        _require_fields(loop, {"init", "condition", "update", "body"}, "a for_ loop")
        variable, init = self._loop_assignment(loop.init, "init")
        update_variable, update = self._loop_assignment(loop.update, "update")
        if update_variable != variable:
            raise QMFakeUnsupportedError("a for_ update must assign the loop variable")
        condition = self._expression(loop.condition)
        body = self._block(loop.body)
        assign = self._assigner(variable)

        def run(state: _ExecutionState) -> None:
            assign(state, init(state.env))
            while condition(state.env):
                # Charge loop control even when the body is empty or makes no progress.
                state.tick()
                for statement in body:
                    state.tick()
                    statement(state)
                assign(state, update(state.env))

        return run

    def _assigner(self, variable: str) -> Callable[[_ExecutionState, Any], None]:
        kind = self._variable_type(variable)

        def assign(state: _ExecutionState, value: Any) -> None:
            if kind == "INT":
                if isinstance(value, (float, bool)):
                    raise QMFakeUnsupportedError(f"assigning {value!r} to int '{variable}'")
                state.env[variable] = _check_int(int(value))
            elif kind == "REAL":
                state.env[variable] = _quantize_fixed(float(value))
            else:
                state.env[variable] = bool(value)

        return assign

    def _variable_type(self, name: str) -> str:
        if name not in self._types:
            raise QMFakeUnsupportedError(f"variable '{name}' is not declared")
        return self._types[name]

    def _element_names(self, references: Any) -> list[str]:
        names = []
        for reference in references:
            _require_fields(reference, {"name"}, "an element reference")
            if not self._config.has_element(reference.name):
                raise QMFakeUnsupportedError(f"element '{reference.name}' is not configured")
            names.append(reference.name)
        return names

    def _play(self, play: Any) -> Statement:
        _require_fields(play, {"qe", "namedPulse", "amp"}, "a play statement")
        if play.WhichOneof("pulseType") != "namedPulse":
            raise QMFakeUnsupportedError("play needs a named operation")
        (element,) = self._element_names([play.qe])
        operation = play.namedPulse.name
        binding = self._by_drive.get(element)
        if binding is None:
            raise QMFakeUnsupportedError(
                f"play on '{element}': only the drive elements of the configured qubits "
                f"({', '.join(sorted(self._by_drive))}) are supported"
            )
        angle_per_amp = math.pi * self._config.envelope_area(element, operation)
        angle_per_amp /= binding.pi_pulse_area
        amplitude: Expr = lambda _env: 1.0  # noqa: E731
        if play.HasField("amp"):
            _require_fields(play.amp, {"v0"}, "an amp() multiplier")
            amplitude = self._expression(play.amp.v0)
        qid = binding.qid

        def run(state: _ExecutionState) -> None:
            value = amplitude(state.env)
            if isinstance(value, bool) or not AMP_MIN <= float(value) < AMP_MAX:
                raise QMFakeUnsupportedError(f"amp({value!r}) is outside the QUA range [-2, 2)")
            state.rotation[qid] += angle_per_amp * float(value)
            state.played_amplitudes.setdefault(f"{element}.{operation}", []).append(float(value))

        return run

    def _measure(self, measure: Any) -> Statement:
        _require_fields(measure, {"qe", "pulse", "measureProcesses"}, "a measure statement")
        (element,) = self._element_names([measure.qe])
        _require_fields(measure.pulse, {"name"}, "a measured operation")
        operation = measure.pulse.name
        binding = self._by_readout.get(element)
        if binding is None:
            raise QMFakeUnsupportedError(
                f"measure on '{element}': only the readout elements of the configured qubits "
                f"({', '.join(sorted(self._by_readout))}) are supported"
            )
        targets = [
            self._measure_process(p, element, operation, binding) for p in measure.measureProcesses
        ]
        if not targets:
            raise QMFakeUnsupportedError("measure without a demodulation process is not supported")
        qid = binding.qid

        def run(state: _ExecutionState) -> None:
            theta = state.rotation[qid]
            state.rotation[qid] = 0.0
            index = len(state.probabilities)
            state.probabilities.append(math.sin(theta / 2.0) ** 2)
            state.measured_qids.append(qid)
            for variable, re_coefficient, im_coefficient in targets:
                state.env[variable] = _MeasuredValue(index, re_coefficient, im_coefficient)

        return run

    def _measure_process(
        self, process: Any, element: str, operation: str, binding: _QubitBinding
    ) -> tuple[str, float, float]:
        _require_fields(process, {"analog"}, "a measure process")
        analog = process.analog
        kind = analog.WhichOneof("process")
        if kind == "demodIntegration":
            demod = analog.demodIntegration
            _require_fields(demod, {"integration", "target", "elementOutput"}, "demod.full")
            parts = [(demod.integration, demod.elementOutput)]
        elif kind == "dualDemodIntegration":
            demod = analog.dualDemodIntegration
            _require_fields(
                demod,
                {"integration1", "integration2", "target", "elementOutput1", "elementOutput2"},
                "dual_demod.full",
            )
            parts = [
                (demod.integration1, demod.elementOutput1),
                (demod.integration2, demod.elementOutput2),
            ]
        else:
            raise QMFakeUnsupportedError(f"measure process '{kind}' is not supported")
        target = demod.target
        if target.WhichOneof("processTarget") != "scalarProcess":
            raise QMFakeUnsupportedError("sliced or accumulated demodulation is not supported")
        scalar = target.scalarProcess
        if scalar.WhichOneof("target") != "variable":
            raise QMFakeUnsupportedError("demodulation into an array cell is not supported")
        variable = scalar.variable.name
        if self._variable_type(variable) != "REAL":
            raise QMFakeUnsupportedError(f"demodulation target '{variable}' must be fixed")

        re_coefficient = im_coefficient = 0.0
        for integration, output in parts:
            _require_fields(integration, {"name"}, "an integration weight reference")
            if output not in binding.outputs:
                raise QMFakeUnsupportedError(
                    f"output '{output}' is not one of the outputs {list(binding.outputs)} "
                    f"configured for qubit {binding.qid}"
                )
            if output not in self._config.element(element).outputs:
                raise QMFakeUnsupportedError(f"element '{element}' has no output '{output}'")
            weight = self._config.demod_weight(element, operation, integration.name)
            if binding.outputs.index(output) == 0:
                # z = s: Re z = Re s, Im z = Im s
                re_coefficient += weight.cosine / 2.0
                im_coefficient -= weight.sine / 2.0
            else:
                # z = -i s: Re z = Im s, Im z = -Re s
                re_coefficient += weight.sine / 2.0
                im_coefficient += weight.cosine / 2.0
        return variable, DEMOD_SCALE * re_coefficient, DEMOD_SCALE * im_coefficient

    def _align(self, align: Any) -> Statement:
        _require_fields(align, {"qe"}, "an align statement")
        self._element_names(align.qe)
        return lambda _state: None

    def _wait(self, wait: Any) -> Statement:
        _require_fields(wait, {"qe", "time"}, "a wait statement")
        self._element_names(wait.qe)
        duration = self._expression(wait.time)

        def run(state: _ExecutionState) -> None:
            cycles = duration(state.env)
            if isinstance(cycles, (bool, float)) or cycles < 4:
                raise QMFakeUnsupportedError(f"wait({cycles!r}) needs at least 4 clock cycles")

        return run

    def _save(self, save: Any) -> Statement:
        _require_fields(save, {"tag", "source"}, "a save statement")
        source = save.source
        if source.WhichOneof("source") != "variable":
            raise QMFakeUnsupportedError("save needs a scalar variable")
        _require_fields(source.variable, {"name"}, "a saved variable")
        variable = source.variable.name
        self._variable_type(variable)
        tag = save.tag
        self.saved_tags.add(tag)

        def run(state: _ExecutionState) -> None:
            state.streams.setdefault(tag, []).append(state.env[variable])

        return run

    # -- expressions ----------------------------------------------------------------

    def _expression(self, expression: Any) -> Expr:
        kind = expression.WhichOneof("expression_oneof")
        if kind == "literal":
            literal = expression.literal
            _require_fields(literal, {"value", "type"}, "a literal")
            constant = self._literal_value(literal, self._type_names[literal.type])
            return lambda _env: constant
        if kind == "variable":
            _require_fields(expression.variable, {"name"}, "a variable reference")
            name = expression.variable.name
            self._variable_type(name)

            def read(env: Env) -> int | float | bool:
                value = env[name]
                if isinstance(value, _MeasuredValue):
                    raise QMFakeUnsupportedError(
                        f"computing with the measured variable '{name}' is not supported"
                    )
                return value

            return read
        if kind == "binaryOperation":
            binary = expression.binaryOperation
            _require_fields(binary, {"op", "left", "right"}, "a binary operation")
            op_name = self._binary_op_names[binary.op]
            left = self._expression(binary.left)
            right = self._expression(binary.right)
            if op_name in _COMPARISONS:
                compare = _COMPARISONS[op_name]
                return lambda env: compare(left(env), right(env))
            if op_name in _ARITHMETIC:
                arithmetic = _ARITHMETIC[op_name]

                def evaluate(env: Env) -> int | float:
                    a, b = left(env), right(env)
                    if isinstance(a, float) or isinstance(b, float):
                        return _quantize_fixed(arithmetic(float(a), float(b)))
                    return _check_int(arithmetic(int(a), int(b)))

                return evaluate
            raise QMFakeUnsupportedError(f"QUA operator {op_name} is not supported")
        raise QMFakeUnsupportedError(f"QUA expression '{kind}' is not supported")


# ---------------------------------------------------------------------------
# Stream processing
# ---------------------------------------------------------------------------


@dataclass
class _Stream:
    """Items emitted by a stream-processing pipeline; each item is a scalar or an array."""

    items: list[npt.NDArray[np.float64] | float | int]


def _value_tree(value: Any) -> Any:
    kind = value.WhichOneof("kind")
    if kind == "string_value":
        return value.string_value
    if kind == "list_value":
        return [_value_tree(item) for item in value.list_value.values]
    raise QMFakeUnsupportedError(f"stream processing node of kind {kind} is not supported")


def _parse_positive_int(text: Any, what: str) -> int:
    if not isinstance(text, str) or not text.isdigit() or int(text) < 1:
        raise QMFakeUnsupportedError(f"{what} {text!r} is not a positive integer")
    return int(text)


def _run_pipeline(node: Any, raw: dict[str, list[Any]]) -> _Stream:
    if not isinstance(node, list) or not node:
        raise QMFakeUnsupportedError(f"stream processing node {node!r} is not supported")
    head = node[0]
    if head == "@re" and len(node) == 3 and node[1] == "0" and isinstance(node[2], str):
        if node[2] not in raw:
            return _Stream(items=[])
        return _Stream(items=list(raw[node[2]]))
    if head == "buffer" and len(node) == 3:
        size = _parse_positive_int(node[1], "buffer size")
        inner = _run_pipeline(node[2], raw)
        complete = len(inner.items) // size
        items = [
            np.asarray(inner.items[i * size : (i + 1) * size], dtype=float) for i in range(complete)
        ]
        return _Stream(items=list(items))
    if head == "average" and len(node) == 2:
        inner = _run_pipeline(node[1], raw)
        running: list[npt.NDArray[np.float64] | float | int] = []
        total: Any = None
        for count, item in enumerate(inner.items, start=1):
            total = np.asarray(item, dtype=float) if total is None else total + item
            running.append(np.asarray(total / count, dtype=float))
        return _Stream(items=running)
    raise QMFakeUnsupportedError(
        f"stream processing operator {head!r} is not supported by the qm-fake device"
    )


def _decode_result_analysis(qua_program: Any) -> dict[str, Any]:
    """Return ``{result name: pipeline tree}`` for every ``save`` in the stream processing."""
    outputs: dict[str, Any] = {}
    for model in qua_program.resultAnalysis.model:
        tree = [_value_tree(value) for value in model.values]
        if len(tree) != 3 or tree[0] != "save" or not isinstance(tree[1], str):
            raise QMFakeUnsupportedError(
                f"stream processing output {tree[:2]!r} is not supported; only save() is"
            )
        if tree[1] in outputs:
            raise QMFakeUnsupportedError(f"stream processing saves '{tree[1]}' twice")
        outputs[tree[1]] = tree[2]
    return outputs


# ---------------------------------------------------------------------------
# SDK-shaped manager, machine, job and result handles
# ---------------------------------------------------------------------------


class QMFakeStreamFetcher:
    """Result of one named stream, shaped like the SDK's ``SingleStreamSingleResultFetcher``."""

    def __init__(self, name: str, value: Any) -> None:
        self.name = name
        self._value = value

    def wait_for_all_values(self, timeout: float | None = None) -> bool:
        """All values exist once ``execute`` returns."""
        return True

    def fetch_all(self, *, check_for_errors: bool = True, flat_struct: bool = False) -> Any:
        """Return the last value the pipeline saved, or ``None`` when it saved nothing."""
        return None if self._value is None else np.array(self._value, copy=True)

    def fetch(
        self,
        item: int | slice,
        *,
        check_for_errors: bool = True,
        flat_struct: bool = False,
        timeout: float | None = None,
    ) -> Any:
        """A ``save()`` result holds a single value, as in the SDK."""
        return self.fetch_all()


class QMFakeResultHandles:
    """Named results of a fake job, shaped like the SDK's ``StreamsManager``."""

    def __init__(self, fetchers: dict[str, QMFakeStreamFetcher]) -> None:
        self._fetchers = fetchers

    def wait_for_all_values(self, timeout: float | None = None) -> bool:
        """The fake job completes inside ``execute``; nothing is pending."""
        return True

    def is_processing(self) -> bool:
        """Never processing once ``execute`` returns."""
        return False

    def get(self, name: str, /, default: Any = None) -> QMFakeStreamFetcher | None:
        """Return the handle of a named result, or ``None`` when the program saved no such name."""
        return self._fetchers.get(name)

    def keys(self) -> list[str]:
        """Names of the results the program's stream processing saves."""
        return list(self._fetchers)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._fetchers


class QMFakeJob:
    """Completed fake job. ``fake_report`` describes what the device executed."""

    def __init__(self, job_id: str, handles: QMFakeResultHandles, report: dict[str, Any]) -> None:
        self.id = job_id
        self.result_handles = handles
        self.fake_report = report

    @property
    def status(self) -> str:
        """The fake job runs to completion inside ``execute``."""
        return "completed"


class QMFakeQuantumMachine:
    """Quantum machine opened on the fake device; executes the supported QUA subset."""

    def __init__(self, manager: QMFakeQuantumMachinesManager, pb_config: Any, qm_id: str) -> None:
        self._manager = manager
        self._config = _ConfigView(pb_config)
        self.id = qm_id
        self._closed = False
        self._jobs = itertools.count(1)

    @property
    def closed(self) -> bool:
        """Whether ``close`` was called."""
        return self._closed

    def close(self) -> bool:
        """Close the machine; later ``execute`` calls fail."""
        self._closed = True
        return True

    def execute(self, program: Any) -> QMFakeJob:
        """Interpret ``program`` and return a completed job with its stream results.

        Only the program argument of ``QuantumMachine.execute`` is accepted: the fake
        device neither simulates nor takes compiler options.
        """
        if self._closed:
            raise RuntimeError("The quantum machine is closed")
        from qm import Program

        if not isinstance(program, Program):
            raise TypeError("program argument must be of type qm.program.Program")
        self._manager.capabilities.validate(program.used_capabilities)
        qua_program = program.qua_program
        return self._manager.run(self, qua_program, f"{self.id}-job{next(self._jobs)}")

    @property
    def config_view(self) -> _ConfigView:
        """Configuration the machine was opened with."""
        return self._config


class QMFakeQuantumMachinesManager:
    """Stand-in for ``qm.QuantumMachinesManager`` backed by the qm-fake device model.

    It never opens a network connection. The QUA configuration is validated with the
    installed SDK's ``load_config`` against the capabilities of the configured QOP
    major version.
    """

    def __init__(self, settings: QMFakeSettings) -> None:
        from qm import QopCaps
        from qm.api.models.capabilities import ServerCapabilities

        caps = QopCaps.get_all() if settings.qop_version == 3 else QopCaps.qop2_caps()
        self.capabilities = ServerCapabilities(caps)
        self._settings = settings
        self._rng = np.random.default_rng(settings.seed)
        self._machines: list[QMFakeQuantumMachine] = []
        self._ids = itertools.count(1)
        self._closed = False
        self._bindings = {
            qid: _QubitBinding(
                qid=qid,
                drive_element=binding.qubit_element,
                readout_element=binding.readout_element,
                outputs=tuple(binding.outputs),
                pi_pulse_area=settings.device[qid].pi_pulse_area,
            )
            for qid, binding in settings.qubits.items()
        }

    @property
    def closed(self) -> bool:
        """Whether ``close`` was called."""
        return self._closed

    def open_qm(
        self, config: dict[str, Any], close_other_machines: bool | None = None
    ) -> QMFakeQuantumMachine:
        """Validate ``config`` with the SDK and open a quantum machine on the fake device."""
        if self._closed:
            raise RuntimeError("The qm-fake manager is closed; connect the backend again")
        from qm.program import load_config

        pb_config = load_config(cast("Any", config), capabilities=self.capabilities)
        if close_other_machines is False and any(not m.closed for m in self._machines):
            raise QMFakeUnsupportedError("the qm-fake device runs one quantum machine at a time")
        for machine in self._machines:
            machine.close()
        machine = QMFakeQuantumMachine(self, pb_config, f"qm-fake-{next(self._ids)}")
        self._machines = [machine]
        return machine

    def close(self) -> None:
        """Close every open machine; later ``open_qm`` calls fail."""
        for machine in self._machines:
            machine.close()
        self._closed = True

    def run(self, machine: QMFakeQuantumMachine, qua_program: Any, job_id: str) -> QMFakeJob:
        """Interpret a program on ``machine`` and draw the measured responses."""
        compiler = _ProgramCompiler(qua_program, machine.config_view, self._bindings)
        statements = compiler.compile()
        outputs = _decode_result_analysis(qua_program)
        state = _ExecutionState(
            env=dict(compiler.initial_env), rotation=dict.fromkeys(self._bindings, 0.0)
        )
        for statement in statements:
            state.tick()
            statement(state)

        responses = self._draw_responses(state)
        raw = {
            tag: _resolve_stream(tag, values, responses) for tag, values in state.streams.items()
        }
        fetchers: dict[str, QMFakeStreamFetcher] = {}
        for name, pipeline in outputs.items():
            items = _run_pipeline(pipeline, raw).items
            fetchers[name] = QMFakeStreamFetcher(name, items[-1] if items else None)
        report = {
            "job_id": job_id,
            "measurements": len(state.probabilities),
            "statements_executed": state.executed,
            "plays": {
                key: {
                    "count": len(values),
                    "distinct_amplitudes": len(set(values)),
                    "min_amplitude": min(values),
                    "max_amplitude": max(values),
                }
                for key, values in state.played_amplitudes.items()
            },
            "results": {
                name: list(np.shape(fetcher.fetch_all())) for name, fetcher in fetchers.items()
            },
        }
        return QMFakeJob(job_id, QMFakeResultHandles(fetchers), report)

    def _draw_responses(self, state: _ExecutionState) -> npt.NDArray[np.complex128]:
        count = len(state.probabilities)
        if count == 0:
            return np.zeros(0, dtype=np.complex128)
        probabilities = np.asarray(state.probabilities, dtype=float)
        excited = self._rng.random(count) < probabilities
        responses = np.empty(count, dtype=np.complex128)
        noise = self._rng.standard_normal(count) + 1j * self._rng.standard_normal(count)
        qids = np.asarray(state.measured_qids)
        for qid in set(state.measured_qids):
            physics = self._settings.device[qid]
            mask = qids == qid
            ground = complex(*physics.ground_iq)
            excited_point = complex(*physics.excited_iq)
            responses[mask] = np.where(excited[mask], excited_point, ground)
            responses[mask] += physics.noise_per_shot * noise[mask]
        return responses


def _resolve_stream(
    tag: str, values: list[Value], responses: npt.NDArray[np.complex128]
) -> list[Any]:
    """Replace measured placeholders with fixed-point demodulated values."""
    measured = [v for v in values if isinstance(v, _MeasuredValue)]
    if not measured:
        return [float(v) if isinstance(v, float) else v for v in values]
    if len(measured) != len(values):
        raise QMFakeUnsupportedError(f"stream {tag} mixes measured and computed values")
    index = np.fromiter((v.measurement for v in measured), dtype=np.int64, count=len(measured))
    re_c = np.fromiter((v.re_coefficient for v in measured), dtype=float, count=len(measured))
    im_c = np.fromiter((v.im_coefficient for v in measured), dtype=float, count=len(measured))
    selected = responses[index]
    demodulated = re_c * selected.real + im_c * selected.imag
    if np.any(demodulated < FIXED_MIN) or np.any(demodulated >= FIXED_MAX):
        raise QMFakeUnsupportedError(f"demodulated values of stream {tag} overflow QUA fixed")
    return list(np.round(demodulated * FIXED_SCALE) / FIXED_SCALE)
