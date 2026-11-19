"""Shared Hypothesis strategies for engine-level property tests."""
from hypothesis import strategies as st

from tests.conftest import CORPUS_NAMES, corpus_bytes


@st.composite
def mutated_corpus(draw):
    """A corpus file with byte flips, then optional truncation and extension."""
    data = bytearray(corpus_bytes(draw(st.sampled_from(CORPUS_NAMES))))
    if data:
        flips = draw(st.lists(
            st.tuples(st.integers(0, len(data) - 1), st.integers(1, 255)),
            max_size=16))
        for pos, mask in flips:
            data[pos] ^= mask
    if draw(st.booleans()):
        data = data[:draw(st.integers(0, len(data)))]
    if draw(st.booleans()):
        data += draw(st.binary(max_size=1024))
    return bytes(data)


engine_inputs = st.one_of(st.binary(max_size=65536), mutated_corpus())
