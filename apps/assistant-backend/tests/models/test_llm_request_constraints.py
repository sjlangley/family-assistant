"""Characterisation tests for LLM request field validation bounds."""

from typing import Any

from pydantic import ValidationError
import pytest

from assistant.models.llm import (
    CreateChatCompletionRequest,
    CreateCompletionRequest,
)

BOTH = (CreateCompletionRequest, CreateChatCompletionRequest)

# field -> (lower bound or None, upper bound or None, models having the field)
# Bounds are inclusive.
CONSTRAINTS: dict[str, tuple[Any, Any, tuple[type, ...]]] = {
    'max_tokens': (0, None, (CreateCompletionRequest,)),
    'min_tokens': (0, None, BOTH),
    'logprobs': (0, None, (CreateCompletionRequest,)),
    'top_logprobs': (0, None, (CreateChatCompletionRequest,)),
    'top_k': (0, None, BOTH),
    'top_p': (0.0, 1.0, BOTH),
    'min_p': (0.0, 1.0, BOTH),
    'presence_penalty': (-2.0, 2.0, BOTH),
    'frequency_penalty': (-2.0, 2.0, BOTH),
    'repeat_penalty': (0.0, None, BOTH),
    'mirostat_mode': (0, 2, BOTH),
    'mirostat_tau': (0.0, 10.0, BOTH),
    'mirostat_eta': (0.001, 1.0, BOTH),
}


def _step(bound: Any) -> Any:
    # Probes 0.001 outside each float bound, so outward drift of 0.001 or more
    # fails (e.g. mirostat_eta 0.001 -> 0.0); smaller drift is not caught.
    return 1 if isinstance(bound, int) else 0.001


def _cases() -> tuple[list[Any], list[Any]]:
    invalid: list[Any] = []
    valid: list[Any] = []
    for field, (low, high, models) in CONSTRAINTS.items():
        for model in models:
            if low is not None:
                invalid.append((model, field, low - _step(low)))
                valid.append((model, field, low))
            if high is not None:
                invalid.append((model, field, high + _step(high)))
                valid.append((model, field, high))
            valid.append((model, field, None))
    return invalid, valid


INVALID_CASES, VALID_CASES = _cases()


def _id(case: Any) -> str:
    model, field, value = case
    return f'{model.__name__}-{field}-{value}'


@pytest.mark.parametrize('case', INVALID_CASES, ids=_id)
def test_value_outside_bound_is_rejected(case: Any) -> None:
    model, field, value = case
    with pytest.raises(ValidationError):
        model(**{field: value})


@pytest.mark.parametrize('case', VALID_CASES, ids=_id)
def test_boundary_and_none_are_accepted(case: Any) -> None:
    model, field, value = case
    assert getattr(model(**{field: value}), field) == value


@pytest.mark.parametrize(
    ('model', 'field'),
    [(m, f) for f, (_, _, models) in CONSTRAINTS.items() for m in models],
    ids=lambda x: getattr(x, '__name__', x),
)
def test_default_is_within_bounds(model: type, field: str) -> None:
    # Pydantic does not validate defaults, so check them against the bounds.
    low, high, _ = CONSTRAINTS[field]
    default = model.model_fields[field].default
    if default is None:
        return
    assert low is None or default >= low
    assert high is None or default <= high


@pytest.mark.parametrize('model', BOTH)
def test_defaults_validate(model: type) -> None:
    request = model()
    assert request.top_p == 0.95
    assert request.min_p == 0.05
    assert request.presence_penalty == 0.0
    assert request.frequency_penalty == 0.0
    assert request.top_k == 40
    assert request.repeat_penalty == 1.1
    assert request.mirostat_mode == 0
    assert request.mirostat_tau == 5.0
    assert request.mirostat_eta == 0.1
    assert request.min_tokens == 0


def test_completion_default_max_tokens() -> None:
    assert CreateCompletionRequest().max_tokens == 16
