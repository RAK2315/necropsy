"""Tests for tools/adversary.py: the generator is blind, and the respelled rule is applied and reported apart.

The adversary is a measurement (design.md, "Finding"), so these tests check the
instrument, not that closure count is zero.
"""
import inspect

from necropsy.engine import Engine
from necropsy.engine.closure import check_closure
from necropsy.engine.types import hypothesis_key
from tests.conftest import corpus_bytes
from tools import adversary


def _ident(h):
    return hypothesis_key(h) + (h.probe_name,)


def test_generator_takes_only_a_size():
    params = list(inspect.signature(adversary.generate_layouts).parameters)
    assert params == ["size"]


def test_generator_is_deterministic_and_has_no_duplicates():
    first = [_ident(h) for h in adversary.generate_layouts(11)]
    second = [_ident(h) for h in adversary.generate_layouts(11)]
    assert first == second
    assert len(first) == len(set(first))


def test_generator_ignores_non_size_input():
    assert list(adversary.generate_layouts(-1)) == []
    assert list(adversary.generate_layouts("11")) == []
    assert list(adversary.generate_layouts(True)) == []


def test_generator_covers_the_decision_record_4_class():
    # mystery_b's naive 7x7, header 128, RLE: the layout Decision Record 4 says closed before the fix.
    idents = {(h.width, h.height, h.bit_depth, h.header_size, h.encoding)
              for h in adversary.generate_layouts(955)}
    assert (7, 7, 8, 128, "rle_pcx") in idents


def test_respelled_closures_are_counted_apart_from_closed():
    data = corpus_bytes("mystery_e")
    result = Engine().run(data)
    c = adversary.run_adversary(data, result)
    assert c.respelled > 0                       # same physical layout, different key
    assert c.generated == c.excluded + c.tried
    # Every respelled layout is a physical copy of the reported candidate, so none is in closed_examples.
    cand = result.candidate
    for h in c.closed_examples:
        v = check_closure(h, data)
        assert adversary._physical(h, v) != (
            cand.hypothesis.width, cand.hypothesis.height, cand.hypothesis.bit_depth,
            cand.hypothesis.header_size, cand.row_stride, cand.hypothesis.encoding,
            cand.data_start, cand.data_end)
