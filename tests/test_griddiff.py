"""grid_diff: an ablation is a claim that exactly one thing changed."""

from __future__ import annotations

import pytest

from mlragents import griddiff


def write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_flatten_uses_dotted_keys_and_indexes_sequences():
    flat = griddiff.flatten({"model": {"kernel": "elu"}, "defaults": ["a", "b"]})
    assert flat == {"model.kernel": "elu", "defaults[0]": "a", "defaults[1]": "b"}


def test_flatten_reaches_values_nested_below_a_list():
    flat = griddiff.flatten({"stages": [{"lr": 1}, {"lr": 2}]})
    assert flat == {"stages[0].lr": 1, "stages[1].lr": 2}


def test_diff_ignores_key_order_and_comments(tmp_path):
    left = write(tmp_path, "a.yaml", "# a comment\nmodel:\n  kernel: elu\n  depth: 4\n")
    right = write(tmp_path, "b.yaml", "model:\n  depth: 4\n  kernel: elu\n")
    assert griddiff.diff(left, right).differences == []


def test_diff_reports_the_changed_leaf_not_the_containing_block(tmp_path):
    left = write(tmp_path, "a.yaml", "model:\n  kernel: elu\n  depth: 4\n")
    right = write(tmp_path, "b.yaml", "model:\n  kernel: softmax\n  depth: 4\n")
    result = griddiff.diff(left, right)
    assert result.keys == ["model.kernel"]
    assert (result.differences[0].left, result.differences[0].right) == ("elu", "softmax")


def test_diff_records_which_side_a_key_is_missing_from(tmp_path):
    left = write(tmp_path, "a.yaml", "model:\n  kernel: elu\n")
    right = write(tmp_path, "b.yaml", "model:\n  kernel: elu\n  scale: 2\n")
    (only,) = griddiff.diff(left, right).differences
    assert (only.key, only.present_in, only.right) == ("model.scale", "right", 2)


def test_diff_compares_across_formats(tmp_path):
    left = write(tmp_path, "a.yaml", "model:\n  kernel: elu\n")
    right = write(tmp_path, "b.json", '{"model": {"kernel": "elu"}}')
    assert griddiff.diff(left, right).differences == []


def test_unsupported_suffix_is_refused_by_name(tmp_path):
    path = write(tmp_path, "a.txt", "model: elu")
    with pytest.raises(griddiff.UnsupportedConfig, match=r"\.txt"):
        griddiff.load(path)


def test_verdict_passes_when_only_the_axis_differs(tmp_path):
    left = write(tmp_path, "a.yaml", "model:\n  kernel: elu\nseed: 0\n")
    right = write(tmp_path, "b.yaml", "model:\n  kernel: softmax\nseed: 0\n")
    result = griddiff.verdict(griddiff.diff(left, right), ["model.kernel"])
    assert result["ok"] is True
    assert result["violations"] == []


def test_verdict_flags_a_second_axis_that_crept_in(tmp_path):
    left = write(tmp_path, "a.yaml", "model:\n  kernel: elu\nlr: 0.001\n")
    right = write(tmp_path, "b.yaml", "model:\n  kernel: softmax\nlr: 0.01\n")
    result = griddiff.verdict(griddiff.diff(left, right), ["model.kernel"])
    assert result["ok"] is False
    assert result["violations"] == ["lr"]
    assert "do not isolate" in result["summary"]


def test_verdict_flags_an_axis_that_did_not_actually_change(tmp_path):
    left = write(tmp_path, "a.yaml", "model:\n  kernel: elu\nseed: 0\n")
    right = write(tmp_path, "b.yaml", "model:\n  kernel: elu\nseed: 1\n")
    result = griddiff.verdict(griddiff.diff(left, right), ["model.kernel"])
    assert result["ok"] is False
    assert result["axes_that_did_not_change"] == ["model.kernel"]


def test_axis_matching_respects_key_boundaries():
    assert griddiff.under_axis("model.kernel", "model.kernel")
    assert griddiff.under_axis("model.kernel.name", "model.kernel")
    assert not griddiff.under_axis("model.kernel_scale", "model.kernel")


def test_axis_matching_covers_indexed_children():
    assert griddiff.under_axis("defaults[0]", "defaults")


def test_no_declared_axis_judges_nothing(tmp_path):
    left = write(tmp_path, "a.yaml", "lr: 1\n")
    right = write(tmp_path, "b.yaml", "lr: 2\n")
    result = griddiff.verdict(griddiff.diff(left, right), None)
    assert result["ok"] is None
    assert "nothing was checked" in result["summary"]


def test_several_axes_are_all_permitted(tmp_path):
    left = write(tmp_path, "a.yaml", "kernel: elu\nnorm: pre\n")
    right = write(tmp_path, "b.yaml", "kernel: softmax\nnorm: post\n")
    result = griddiff.verdict(griddiff.diff(left, right), ["kernel", "norm"])
    assert result["ok"] is True
