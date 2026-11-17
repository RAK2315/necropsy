from hypothesis import given, strategies as st

from coherence import score

KEYS = ["width", "height", "bit_depth", "data_size", "remaining_bytes"]

values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=True, allow_infinity=True)
    | st.text()
    | st.binary(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=10,
)

keys = st.sampled_from(KEYS) | st.text() | st.integers()


@given(st.dictionaries(keys, values))
def test_score_never_raises_and_is_bounded(fields):
    result = score(fields)
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


@given(st.fixed_dictionaries({k: st.integers() for k in KEYS}))
def test_score_bounded_on_all_integer_fields(fields):
    result = score(fields)
    assert 0.0 <= result <= 1.0


def test_plausible_structure_scores_high():
    fields = {"width": 16, "height": 16, "bit_depth": 24,
              "data_size": 768, "remaining_bytes": 768}
    assert score(fields) == 1.0
